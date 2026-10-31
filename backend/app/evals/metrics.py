from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from contracts import DetectionMetrics, EvalCaseResult, EvalRun, ScenarioScore, TypologyEval

GATES = {"account_takeover": 9, "false_positive": 8, "loan_diversion": 9}  # correct out of 10
MAX_GROWTH = 1.25  # time and model calls per Investigation


def detection_metrics(rows: Iterable[Mapping[str, Any]]) -> DetectionMetrics:
    """Each row has `flagged`, `is_fraud` and `story`."""
    tp = fp = fn = tn = 0
    misses: Counter[str] = Counter()
    for row in rows:
        if row["flagged"] and row["is_fraud"]:
            tp += 1
        elif row["flagged"]:
            fp += 1
        elif row["is_fraud"]:
            fn += 1
            misses[row["story"]] += 1
        else:
            tn += 1
    return DetectionMetrics(
        precision=tp / (tp + fp) if tp + fp else 0.0,
        recall=tp / (tp + fn) if tp + fn else 0.0,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        misses_by_story=dict(misses),
    )


def scenario_score(name: str, results: list[EvalCaseResult]) -> ScenarioScore:
    correct = sum(r.passed for r in results)
    gate = GATES[name]
    # Scaled, so a smaller rehearsal run is judged by the same rate.
    return ScenarioScore(
        name=name,
        correct=correct,
        runs=len(results),
        gate=gate,
        passed=bool(results) and correct * 10 >= gate * len(results),
    )


def keep_check(run: EvalRun, typology: TypologyEval, baseline: dict[str, Any]) -> tuple[bool, list[str]]:
    """The keep-or-drop bar. Every line must hold, and each failure is named."""
    scores = {s.name: s for s in run.scenarios}
    reasons = []
    for name in ("false_positive", "account_takeover"):
        score = scores.get(name)
        if score is None or not score.passed:
            reasons.append(f"{name} missed its gate: {score.correct if score else 0} of {score.runs if score else 0}.")
    if run.injection_passed != run.injection_total:
        reasons.append(f"Injection fell to {run.injection_passed} of {run.injection_total}.")
    if run.held_out_correct < baseline["held_out_correct"]:
        reasons.append(f"Held-out fell from {baseline['held_out_correct']} to {run.held_out_correct}.")
    for field, label in (("calls_per_investigation", "Model calls"), ("seconds_per_investigation", "Time")):
        now, before = getattr(typology, field), baseline.get(field)
        if before and now > before * MAX_GROWTH:
            reasons.append(f"{label} per Investigation rose from {before:.1f} to {now:.1f}.")
    return not reasons, reasons

