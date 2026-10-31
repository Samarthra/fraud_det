from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from contracts import DetectionMetrics, EvalCaseResult, ScenarioScore

GATES = {"account_takeover": 9, "false_positive": 8}  # correct out of 10


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
    correct = sum(r.assessment == r.expected for r in results)
    gate = GATES[name]
    # Scaled, so a smaller rehearsal run is judged by the same rate.
    return ScenarioScore(
        name=name,
        correct=correct,
        runs=len(results),
        gate=gate,
        passed=bool(results) and correct * 10 >= gate * len(results),
    )
