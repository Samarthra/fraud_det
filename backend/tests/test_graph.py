from types import SimpleNamespace

from agent.graph import answer_followup, run_investigation
from contracts import AnalystScope, Finding, FollowUp, FollowUpDraft, ReportDraft
from fakes import FakeStore

SCOPE = AnalystScope(analyst_id="a1", portfolio="p1")
RAW = SimpleNamespace(response_metadata={"finish_reason": "stop"})


def no_gather(investigation_id, scope, objective, config):
    return []


def draft(statement):
    return ReportDraft(assessment="suspicious", summary="s", limitations=["l"],
                       recommended_actions=["hold_transaction"],
                       findings=[Finding(statement=statement, evidence_ids=["EV-1"])])


def scripted(*results):
    calls = []

    def synthesise(messages, config):
        calls.append(messages)
        return results[len(calls) - 1]

    synthesise.calls = calls
    return synthesise


def ok(statement):
    return {"raw": RAW, "parsed": draft(statement), "parsing_error": None}


GOOD = "Score 100 on ACC-10042."
BAD = "Score 100 on ACC-99999."


def run(*results, gather=no_gather):
    store, synth = FakeStore(), scripted(*results)
    run_investigation("I", SCOPE, store, gather=gather, synthesise=synth)
    return store, synth


def test_verified_on_the_first_attempt():
    store, synth = run(ok(GOOD))
    assert store.report.verification == "verified" and len(synth.calls) == 1
    assert [s.stage for s in store.steps][0] == "triage" and store.steps[-1].stage == "report"
    assert store.evidence[0].kind == "alert"


def test_one_retry_sends_the_errors_back_then_verifies():
    store, synth = run(ok(BAD), ok(GOOD))
    assert store.report.verification == "verified" and len(synth.calls) == 2
    assert "ACC-99999" in synth.calls[1][-1][1]


def test_second_failure_saves_the_draft_as_unverified():
    store, synth = run(ok(BAD), ok(BAD))
    assert store.report.verification == "unverified" and len(synth.calls) == 2
    assert store.report.assessment == "suspicious"
    assert "ACC-99999" in store.report.verification_errors[0]


def test_unparseable_output_twice_gives_an_empty_report():
    bad = {"raw": RAW, "parsed": None, "parsing_error": ValueError("nope")}
    store, _ = run(bad, bad)
    assert store.report.assessment is None and store.report.verification == "unverified"


def test_truncated_output_uses_the_retry():
    cut = {"raw": SimpleNamespace(response_metadata={"finish_reason": "length"}),
           "parsed": draft(GOOD), "parsing_error": None}
    store, synth = run(cut, ok(GOOD))
    assert len(synth.calls) == 2 and store.report.verification == "verified"


def test_a_crash_still_saves_a_report():
    def boom(*args):
        raise RuntimeError("402")

    store, _ = run(gather=boom)
    assert store.report.assessment is None
    assert "RuntimeError" in store.report.limitations[0]


def test_step_limit_becomes_a_limitation():
    store, _ = run(ok(GOOD), gather=lambda *a: ["Evidence gathering stopped at its step limit."])
    assert "step limit" in store.report.limitations[-1]


def follow_up(store, answer_text, ids):
    store.follow_ups["F"] = FollowUp(id="F", question="Q?", asked_at="t")
    chain = SimpleNamespace(invoke=lambda m, c: {"parsed": FollowUpDraft(answer=answer_text, evidence_ids=ids)})
    answer_followup("I", "F", SCOPE, store, answer=chain)
    return store.follow_ups["F"]


def test_follow_up_never_changes_the_report_and_is_checked():
    store, _ = run(ok(GOOD))
    before = store.report.model_copy(deep=True)
    assert follow_up(store, "ACC-10042 scored 100.", ["EV-1"]).verification == "verified"
    assert follow_up(store, "ACC-99999 did it.", ["EV-1"]).verification == "unverified"
    assert follow_up(store, "ACC-10042.", ["EV-99"]).verification == "unverified"
    assert store.report == before
