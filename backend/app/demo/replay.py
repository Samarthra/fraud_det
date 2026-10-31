"""Export a real Investigation, and load it back as a labelled Replay.

Capture from backend/app: python -m demo.capture <investigation_id> <scenario>
"""

import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from contracts import Report, TypologyResult

REPLAYS = Path(__file__).resolve().parents[3] / "replays"
SCENARIO_BY_TRANSACTION = {
    "TXN-50001": "account_takeover",
    "TXN-50002": "false_positive",
    "TXN-50003": "loan_diversion",
}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def replay_file(transaction_id: str | None) -> Path | None:
    scenario = SCENARIO_BY_TRANSACTION.get(transaction_id or "")
    path = REPLAYS / f"{scenario}.json"
    return path if scenario and path.exists() else None


def export(store, investigation_id: str, scenario: str) -> Path:
    investigation = store.get_investigation(investigation_id)
    if investigation is None or investigation.status != "complete":
        raise ValueError(f"{investigation_id} is not a complete Investigation.")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    REPLAYS.mkdir(exist_ok=True)
    path = REPLAYS / f"{scenario}.json"
    path.write_text(
        json.dumps(
            {
                "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "commit": commit,
                "model": "sarvam-105b",
                "investigation": investigation.model_dump(mode="json"),
                "steps": [s.model_dump(mode="json") for s in store.steps(investigation_id)],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    return path


def shift(value: Any, delta: timedelta) -> Any:
    """Moves structured timestamps. Prose is left alone."""
    if isinstance(value, dict):
        return {k: shift(v, delta) for k, v in value.items()}
    if isinstance(value, list):
        return [shift(v, delta) for v in value]
    if isinstance(value, str) and ISO.match(value):
        try:
            return (datetime.fromisoformat(value) + delta).isoformat()
        except ValueError:
            return value
    return value


def load(store, case_id: str, path: Path) -> str:
    """Writes every row at once. The UI's paced reveal does the playing."""
    saved = json.loads(path.read_text())
    delta = datetime.now().astimezone() - datetime.fromisoformat(saved["captured_at"])
    investigation = saved["investigation"]
    new_id = store.start_investigation(case_id)
    for evidence in investigation["evidence"]:
        store.add_evidence(
            new_id,
            evidence["kind"],
            evidence["source_ref"],
            shift(evidence["data"], delta),
            evidence.get("tool_call_id"),
        )
    for step in saved["steps"]:
        store.append_step(new_id, step["stage"], step["type"], step["summary"], step["evidence_ids"])
    if investigation.get("typology"):
        store.save_typology(new_id, TypologyResult.model_validate(investigation["typology"]))
    store.save_report(new_id, Report.model_validate(investigation["report"]))
    store.mark_replay(new_id, saved["captured_at"], investigation.get("trace_url"))
    return new_id
