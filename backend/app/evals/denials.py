"""Plain code checks with no LLM: out-of-scope IDs must be denied and audited."""

import json

from agent.ports import AgentStore
from contracts import AnalystScope
from tools import build_tools


def run_tool_denials(
    store: AgentStore, scope: AnalystScope, account_id: str, device_id: str
) -> tuple[int, list[str]]:
    tools = {t.name: t for t in build_tools(store, "denial-tests", scope)}
    cases = [
        ("get_transactions", {"account_id": account_id}),
        ("get_account", {"account_id": account_id}),
        ("get_account_events", {"account_id": account_id}),
        ("get_device", {"device_id": device_id}),
    ]
    failures = []
    for name, args in cases:
        output = json.loads(tools[name].invoke(args))
        if not (isinstance(output, dict) and "Access denied" in output.get("error", "")):
            failures.append(f"{name} was not denied.")
    return len(cases), failures
