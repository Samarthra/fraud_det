"""Run from backend/app: python -m evals.run [--source fake] [--repeats 10]"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from agent import tracing
from agent.graph import run_investigation
from agent.ports import AgentStore
from contracts import AnalystScope, Assessment, DetectionMetrics, EvalCaseResult, EvalRun

from .checks import check_case, check_injection
from .denials import run_tool_denials
from .injection import PAYLOADS
from .metrics import GATES, scenario_score

RESULTS = Path(__file__).parent / "results" / "latest.json"
REHEARSAL = RESULTS.with_name("rehearsal.json")  # never served to the screen
PROGRESS = RESULTS.with_name("progress.json")
COST_PER_RUN_INR = 0.20
NOTICE = (
    "Measured on synthetic data written by the team. "
    "Recall here does not predict real-world performance."
)


class Source(Protocol):
    scope: AnalystScope
    out_of_scope_account: str
    out_of_scope_device: str

    def scenario(self, name: str) -> AgentStore: ...
    def poisoned(self, field: str, text: str) -> AgentStore: ...
    def held_out(self) -> list[tuple[str, AgentStore, Assessment]]: ...
    def denial_store(self) -> AgentStore: ...
    def detection(self) -> DetectionMetrics | None: ...


Investigate = Callable[[str, AnalystScope, AgentStore], None]


def write_progress(done: int, total: int, current: str, last_error: str | None = None) -> None:
    PROGRESS.parent.mkdir(exist_ok=True)
    PROGRESS.write_text(
        json.dumps({"done": done, "total": total, "current": current, "last_error": last_error})
    )


def run_case(
    run_id: str,
    case_id: str,
    group: str,
    expected: Assessment,
    store: AgentStore,
    scope: AnalystScope,
    injection: bool = False,
    investigate: Investigate = run_investigation,
) -> EvalCaseResult:
    investigation_id = f"eval-{run_id}-{case_id}"
    started = time.time()
    investigate(investigation_id, scope, store)
    seconds = time.time() - started
    report = store.get_report(investigation_id)
    failures = (
        check_injection(report, store, investigation_id, scope)
        if injection
        else check_case(report, expected)
    )
    tracing.score(investigation_id, not failures, group)
    print(f"{case_id}: {'pass' if not failures else failures} ({seconds:.0f}s)", flush=True)
    return EvalCaseResult(
        case_id=case_id,
        group=group,
        expected=expected,
        assessment=report.assessment if report else None,
        verification=report.verification if report else None,
        failures=failures,
        seconds=seconds,
        trace_url=tracing.trace_url(investigation_id),
    )


def run_suite(
    source: Source,
    repeats: int,
    investigate: Investigate = run_investigation,
    on_case: Callable[[int, int, str], None] = lambda done, total, current: None,
) -> EvalRun:
    run_id = datetime.now(timezone.utc).strftime("%H%M%S")
    scope = source.scope
    cases_to_hold = source.held_out()
    total = repeats * len(GATES) + len(cases_to_hold) + 3 * len(PAYLOADS)
    finished = 0

    def tracked(case_id: str, *args, **kwargs) -> EvalCaseResult:
        nonlocal finished
        on_case(finished, total, case_id)
        result = run_case(run_id, case_id, *args, investigate=investigate, **kwargs)
        finished += 1
        on_case(finished, total, case_id)
        return result

    expected: dict[str, Assessment] = {
        "account_takeover": "suspicious",
        "false_positive": "not_suspicious",
    }
    scenarios = {
        name: [
            tracked(f"{name}-{i}", name, expected[name], source.scenario(name), scope)
            for i in range(repeats)
        ]
        for name in GATES
    }
    held_out = [
        tracked(case_id, "held_out", want, store, scope)
        for case_id, store, want in cases_to_hold
    ]
    injection = [
        tracked(f"{name}-{i}", "injection", "suspicious", source.poisoned(field, text), scope,
                injection=True)
        for name, (field, text) in PAYLOADS.items()
        for i in range(3)
    ]
    denials_total, denial_failures = run_tool_denials(
        source.denial_store(), scope, source.out_of_scope_account, source.out_of_scope_device
    )
    if denial_failures:
        print("DENIAL FAILURES:", denial_failures, file=sys.stderr)

    cases = [r for group in scenarios.values() for r in group] + held_out + injection
    tracing.flush()
    return EvalRun(
        run_at=datetime.now(timezone.utc).isoformat(),
        commit=subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        model="sarvam-105b",
        estimated_cost_inr=round(len(cases) * COST_PER_RUN_INR, 2),
        notice=NOTICE,
        detection=source.detection(),
        scenarios=[scenario_score(name, results) for name, results in scenarios.items()],
        injection_passed=sum(r.passed for r in injection),
        injection_total=len(injection),
        denials_passed=denials_total - len(denial_failures),
        denials_total=denials_total,
        held_out_correct=sum(r.passed for r in held_out),
        held_out_total=len(held_out),
        failures=[r for r in cases if not r.passed],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["db", "fake"], default="db")
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    if args.source == "fake":
        from .fake_source import FakeSource

        source, out = FakeSource(), REHEARSAL
    else:
        from .db_source import DbSource

        source, out = DbSource(), RESULTS
    write_progress(0, 0, "starting")
    try:
        result = run_suite(source, args.repeats, on_case=write_progress)
    except Exception as e:
        write_progress(0, 0, "failed", f"{type(e).__name__}: {e}")
        raise
    out.parent.mkdir(exist_ok=True)
    out.write_text(result.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2, exclude={"failures"}))


if __name__ == "__main__":
    main()
