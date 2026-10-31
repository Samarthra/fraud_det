"""Evidence tools. Scope comes from this closure, never from the model."""

import json
from itertools import count
from typing import Any

import networkx as nx
from langchain_core.tools import tool

from agent.ports import AgentStore
from contracts import AnalystScope, Evidence

UNTRUSTED_FIELDS = {"description", "beneficiary_name", "details", "name"}
MAX_UNTRUSTED = 200


def wrap_untrusted(value: Any) -> Any:
    """Marks free text before it reaches the model. Stored Evidence keeps the original."""
    if isinstance(value, dict):
        return {
            k: _fence(v) if k in UNTRUSTED_FIELDS and isinstance(v, str) else wrap_untrusted(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [wrap_untrusted(v) for v in value]
    return value


def _fence(text: str) -> str:
    clean = text.replace("<untrusted_data>", "").replace("</untrusted_data>", "")
    return f"<untrusted_data>{clean[:MAX_UNTRUSTED]}</untrusted_data>"


def evidence_for_model(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.id,
        "kind": evidence.kind,
        "source_ref": evidence.source_ref,
        "data": wrap_untrusted(evidence.data),
    }


def build_tools(store: AgentStore, investigation_id: str, scope: AnalystScope) -> list:
    calls = count(1)

    def in_portfolio(account_id: str) -> bool:
        return store.account_portfolio(account_id) == scope.portfolio

    def deny(target: str) -> str:
        store.append_step(investigation_id, "evidence", "denied", f"Access denied: {target}")
        store.audit(
            "access_denied",
            investigation_id=investigation_id,
            analyst_id=scope.analyst_id,
            target=target,
        )
        return json.dumps({"error": f"Access denied: {target} is outside this Analyst's Portfolio."})

    def started(summary: str) -> str:
        store.append_step(investigation_id, "evidence", "tool_call", summary)
        store.audit("tool_call", investigation_id=investigation_id, tool=summary)
        return f"call-{next(calls)}"

    def result(call_id: str, records: list[tuple[str, str, dict[str, Any]]]) -> str:
        saved = [
            store.add_evidence(investigation_id, kind, ref, data, call_id)
            for kind, ref, data in records
        ]
        ids = list(dict.fromkeys(e.id for e in saved))
        store.append_step(
            investigation_id, "evidence", "tool_result", f"{len(ids)} record(s) returned", ids
        )
        return json.dumps([evidence_for_model(e) for e in saved], ensure_ascii=False)

    @tool
    def get_transactions(account_id: str) -> str:
        """Get an account's most recent transactions, newest first."""
        call_id = started(f"get_transactions({account_id})")
        if not in_portfolio(account_id):
            return deny(account_id)
        rows = store.get_transactions(account_id, limit=10)
        return result(call_id, [("transaction", r["transaction_id"], r) for r in rows])

    @tool
    def get_account(account_id: str) -> str:
        """Get an account's profile, age and usual spending."""
        call_id = started(f"get_account({account_id})")
        if not in_portfolio(account_id):
            return deny(account_id)
        row = store.get_account(account_id)
        return result(call_id, [("account", account_id, row)] if row else [])

    @tool
    def get_account_events(account_id: str) -> str:
        """Get login failures, password resets, SIM swaps, device and beneficiary changes."""
        call_id = started(f"get_account_events({account_id})")
        if not in_portfolio(account_id):
            return deny(account_id)
        rows = store.get_account_events(account_id, limit=10)
        return result(
            call_id,
            [("account_event", f"{account_id}/{r['type']}/{r['at']}", r) for r in rows],
        )

    @tool
    def get_device(device_id: str) -> str:
        """Get a device's first-seen time and the accounts seen on it."""
        call_id = started(f"get_device({device_id})")
        row = store.get_device(device_id)
        if row is None:
            return result(call_id, [])
        accounts = row.get("accounts", [])
        visible = [a for a in accounts if in_portfolio(a)]
        if not visible:
            return deny(device_id)
        data = {**row, "accounts": visible, "out_of_scope_count": len(accounts) - len(visible)}
        return result(call_id, [("device", device_id, data)])

    @tool
    def get_beneficiary(beneficiary_id: str) -> str:
        """Get a beneficiary's details and when it was first paid."""
        call_id = started(f"get_beneficiary({beneficiary_id})")
        row = store.get_beneficiary(beneficiary_id)
        if row and scope.portfolio not in store.beneficiary_portfolios(beneficiary_id):
            return deny(beneficiary_id)
        return result(call_id, [("beneficiary", beneficiary_id, row)] if row else [])

    @tool
    def analyze_relationships(beneficiary_id: str) -> str:
        """Find which accounts paid a beneficiary in the last 7 days."""
        call_id = started(f"analyze_relationships({beneficiary_id})")
        if scope.portfolio not in store.beneficiary_portfolios(beneficiary_id):
            return deny(beneficiary_id)
        payments = store.beneficiary_payments(beneficiary_id, days=7)
        graph = nx.Graph()
        graph.add_node(beneficiary_id)
        for p in payments:
            graph.add_edge(p["account_id"], beneficiary_id, transaction_id=p["transaction_id"])
            graph.nodes[p["account_id"]]["portfolio"] = p["portfolio"]
        accounts = list(graph.neighbors(beneficiary_id))
        visible = sorted(a for a in accounts if graph.nodes[a]["portfolio"] == scope.portfolio)
        data = {
            "beneficiary_id": beneficiary_id,
            "paying_accounts_7d": len(accounts),
            "in_scope_accounts": visible,
            "out_of_scope_count": len(accounts) - len(visible),
            "derived_from": sorted(graph.edges[a, beneficiary_id]["transaction_id"] for a in visible),
        }
        return result(call_id, [("relationship", beneficiary_id, data)])

    return [
        get_transactions,
        get_account,
        get_account_events,
        get_device,
        get_beneficiary,
        analyze_relationships,
    ]
