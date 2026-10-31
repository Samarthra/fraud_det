"""The Investigation: Triage, Evidence, Synthesis, Verification, Report."""

import json
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from contracts import Alert, AnalystScope, Evidence, Report, ReportDraft
from tools import build_tools, evidence_for_model

from . import llm as models
from . import tracing
from .ports import AgentStore
from .prompts import EVIDENCE_SYSTEM, FOLLOW_UP_SYSTEM, SYNTHESIS_SYSTEM
from .verification import check_statement, complete_citations, verify

RECURSION_LIMIT = 14  # about 6 tool steps


class InvestigationState(TypedDict, total=False):
    investigation_id: str
    case_id: str
    alert: Alert
    scope: AnalystScope  # never sent to the model
    triage: str
    messages: Annotated[list, add_messages]
    evidence: dict[str, Evidence]
    draft: ReportDraft | None
    verification_errors: list[str]
    limitations: list[str]
    attempt: int  # 0 or 1
    report: Report


Gather = Callable[[str, AnalystScope, str, RunnableConfig], list[str]]
Synthesise = Callable[[list, RunnableConfig], dict[str, Any]]


def evidence_pack(evidence: list[Evidence]) -> str:
    return "\n".join(
        json.dumps(evidence_for_model(e), ensure_ascii=False) for e in evidence
    )


def empty_report(reason: str) -> Report:
    return Report(
        assessment=None,
        summary="No report could be drafted.",
        findings=[],
        limitations=[reason],
        recommended_actions=[],
        verification="unverified",
        verification_errors=[reason],
    )


def gather_with_model(store: AgentStore) -> Gather:
    def gather(investigation_id, scope, objective, config) -> list[str]:
        agent = create_agent(
            models.chat_model(),
            build_tools(store, investigation_id, scope),
            system_prompt=EVIDENCE_SYSTEM,
        )
        try:
            agent.invoke(
                {"messages": [{"role": "user", "content": objective}]},
                {**config, "recursion_limit": RECURSION_LIMIT},
            )
        except GraphRecursionError:
            return ["Evidence gathering stopped at its step limit."]
        return []

    return gather


def synthesise_with_model() -> Synthesise:
    chain = models.report_model(models.chat_model())
    return lambda messages, config: chain.invoke(messages, config)


def build_graph(store: AgentStore, gather: Gather, synthesise: Synthesise):
    def step(state, stage, kind, summary):
        store.append_step(state["investigation_id"], stage, kind, summary)

    def triage(state: InvestigationState, config: RunnableConfig):
        alert = state["alert"]
        step(state, "triage", "stage_started", "Reading the Alert")
        reasons = "; ".join(hit.reason for hit in alert.rule_hits)
        objective = (
            f"Investigate Alert {alert.id} on account {alert.account_id}, "
            f"category {alert.category}, risk score {alert.score}. "
            f"Transaction: {alert.transaction_id or 'none'}. "
            f"Device: {alert.device_id or 'none'}. Rules that fired: {reasons}."
        )
        store.add_evidence(
            state["investigation_id"],
            "alert",
            alert.id,
            alert.model_dump(mode="json", exclude={"supporting_records"}),
        )
        step(state, "triage", "stage_finished", f"{alert.category}, score {alert.score}")
        return {"triage": objective}

    def evidence(state: InvestigationState, config: RunnableConfig):
        step(state, "evidence", "stage_started", "Gathering Evidence")
        limits = gather(state["investigation_id"], state["scope"], state["triage"], config)
        found = store.list_evidence(state["investigation_id"])
        step(state, "evidence", "stage_finished", f"{len(found)} Evidence records gathered")
        return {"evidence": {e.id: e for e in found}, "limitations": limits}

    def synthesis(state: InvestigationState, config: RunnableConfig):
        step(state, "synthesis", "stage_started", "Drafting the report")
        pack = evidence_pack(list(state["evidence"].values()))
        messages = [
            ("system", SYNTHESIS_SYSTEM),
            ("user", f"{state['triage']}\n\nEvidence:\n{pack}"),
        ]
        if state.get("attempt"):
            previous = state["draft"].model_dump_json() if state.get("draft") else "unparseable"
            errors = "\n".join(state["verification_errors"])
            messages.append(
                ("user", f"Your previous draft failed.\nDraft: {previous}\nErrors:\n{errors}\n"
                 "Fix each one by citing the record that holds the value, or remove the value.")
            )
        result = synthesise(messages, config)
        raw, draft = result["raw"], result["parsed"]
        errors = [] if draft else [f"Bad output: {result['parsing_error']}"]
        if raw is not None and raw.response_metadata.get("finish_reason") == "length":
            errors.append("Output was truncated.")
        step(state, "synthesis", "stage_finished", "Draft ready" if draft else "Draft unusable")
        return {"draft": draft, "verification_errors": errors}

    def verification(state: InvestigationState, config: RunnableConfig):
        errors = list(state["verification_errors"])
        draft = state["draft"]
        if draft:
            found = list(state["evidence"].values())
            draft = complete_citations(draft, found)
            errors += verify(draft, found)
        summary = "All claims match their Evidence" if not errors else f"{len(errors)} problem(s) found"
        step(state, "verification", "verification", summary)
        store.audit(
            "verification_result",
            investigation_id=state["investigation_id"],
            errors=errors,
            attempt=state.get("attempt", 0),
        )
        return {"draft": draft, "verification_errors": errors, "attempt": state.get("attempt", 0) + 1}

    def after_verification(state: InvestigationState) -> str:
        return "synthesis" if state["verification_errors"] and state["attempt"] < 2 else "report"

    def report(state: InvestigationState, config: RunnableConfig):
        draft, errors = state["draft"], state["verification_errors"]
        if draft is None:
            saved = empty_report("; ".join(errors))
        else:
            data = draft.model_dump()
            data["limitations"] = [*data["limitations"], *state.get("limitations", [])]
            saved = Report(
                **data,
                verification="unverified" if errors else "verified",
                verification_errors=errors,
            )
        store.save_report(state["investigation_id"], saved)
        store.audit("report_saved", investigation_id=state["investigation_id"])
        step(state, "report", "stage_finished", "Report saved")
        return {"report": saved}  # becomes this stage's output in the trace

    graph = StateGraph(InvestigationState)
    for name, node in [
        ("triage", triage),
        ("evidence", evidence),
        ("synthesis", synthesis),
        ("verification", verification),
        ("report", report),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", "evidence")
    graph.add_edge("evidence", "synthesis")
    graph.add_edge("synthesis", "verification")
    graph.add_conditional_edges("verification", after_verification, ["synthesis", "report"])
    graph.add_edge("report", END)
    return graph.compile()


def run_investigation(
    investigation_id: str,
    ctx: AnalystScope,
    store: AgentStore,
    gather: Gather | None = None,
    synthesise: Synthesise | None = None,
) -> None:
    """Always ends with a saved report, so a failed run is still reviewable."""
    try:
        alert = store.get_alert_for_investigation(investigation_id)
        store.audit("investigation_started", investigation_id=investigation_id)
        url = tracing.trace_url(investigation_id)
        if url:  # set first, because the UI stops polling once the report is saved
            store.set_trace_url(investigation_id, url)
        graph = build_graph(
            store, gather or gather_with_model(store), synthesise or synthesise_with_model()
        )
        graph.invoke(
            {
                "investigation_id": investigation_id,
                "case_id": alert.case_id,
                "alert": alert,
                "scope": ctx,
                "attempt": 0,
            },
            tracing.trace_config(investigation_id),
        )
    except Exception as e:
        reason = f"The Investigation failed: {type(e).__name__}"
        store.audit("investigation_failed", investigation_id=investigation_id, reason=str(e))
        store.save_report(investigation_id, empty_report(reason))
    finally:
        tracing.flush()


def answer_followup(
    investigation_id: str, follow_up_id: str, ctx: AnalystScope, store: AgentStore, answer=None
) -> None:
    """Uses existing Evidence only. A failed check labels the answer, with no retry."""
    evidence = store.list_evidence(investigation_id)
    question = store.get_follow_up(follow_up_id).question
    earlier = [f for f in store.list_follow_ups(investigation_id) if f.answer]
    history = "\n".join(f"Q: {f.question}\nA: {f.answer}" for f in earlier)
    report = store.get_report(investigation_id)
    summary = report.summary if report else ""
    messages = [
        ("system", FOLLOW_UP_SYSTEM),
        (
            "user",
            f"Report summary: {summary}\n\nEarlier questions:\n{history}\n\n"
            f"Evidence:\n{evidence_pack(evidence)}\n\nQuestion: {question}",
        ),
    ]
    store.append_step(investigation_id, "follow_up", "stage_started", "Answering the Follow-up")
    try:
        chain = answer or models.follow_up_model(models.chat_model())
        draft = chain.invoke(messages, tracing.trace_config(investigation_id))["parsed"]
    except Exception as e:
        draft, reason = None, type(e).__name__
    else:
        reason = "unusable output"
    if draft is None:
        store.save_followup_answer(
            follow_up_id, f"No answer could be drafted ({reason}).", [], "unverified"
        )
    else:
        by_id = {e.id: e for e in evidence}
        cited = [by_id[i] for i in draft.evidence_ids if i in by_id]
        unknown = set(draft.evidence_ids) - set(by_id)
        ok = cited and not unknown and not check_statement(draft.answer, cited)
        store.save_followup_answer(
            follow_up_id,
            draft.answer,
            [e.id for e in cited],
            "verified" if ok else "unverified",
        )
    store.append_step(investigation_id, "follow_up", "stage_finished", "Answer ready")
    tracing.flush()
