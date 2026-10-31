from datetime import datetime, timedelta, timezone

import pytest

from demo.seed import load_sample
from detection.engine import load_config, scan
from evals.metrics import detection_metrics
from store import Store

NOW = datetime(2026, 10, 31, 16, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))


@pytest.fixture(scope="module")
def store():
    s = Store()
    load_sample(s, NOW)
    return s


@pytest.fixture(scope="module")
def candidates(store):
    return scan(store.detection_inputs(), load_config())


def by_subject(candidates, subject):
    return [c for c in candidates if c.subject_id == subject]


def rules(candidate):
    return {h.rule for h in candidate.hits}


def test_population_size(store):
    assert len(store.detection_inputs()["transactions"]) in range(5000, 8000)


def test_takeover_scores_100_with_every_expected_rule(candidates):
    c = by_subject(candidates, "TXN-50001")[0]
    assert c.score == 100 and c.category == "account_takeover"
    assert {"new_device", "amount_spike", "new_beneficiary", "mule_beneficiary",
            "foreign_ip", "login_failures_then_success"} <= rules(c)


def test_false_positive_scores_70(candidates):
    c = by_subject(candidates, "TXN-50002")[0]
    assert c.score == 70
    assert rules(c) == {"new_device", "amount_spike", "new_beneficiary"}


def test_family_device_scores_low_but_ring_is_actionable(candidates):
    assert by_subject(candidates, "DEV-FAM0")[0].score == 10
    assert by_subject(candidates, "DEV-RING0")[0].score >= 50


def test_login_pattern_and_loan_ring_are_detected(candidates):
    assert any(c.category == "repeated_login_failures" and c.score >= 50 for c in candidates)
    assert any(c.category == "suspicious_loan_application" for c in candidates)


def test_every_level_1_category_reaches_the_analysts(store):
    seen = {a.category for p in ("portfolio-1", "portfolio-2") for a in store.alerts(p)}
    assert {"account_takeover", "suspicious_transfer", "shared_device",
            "repeated_login_failures", "suspicious_loan_application"} <= seen


def test_scenarios_are_in_analyst_ones_queue_only(store):
    one = {a.transaction_id for a in store.alerts("portfolio-1")}
    two = {a.transaction_id for a in store.alerts("portfolio-2")}
    assert {"TXN-50001", "TXN-50002"} <= one and not {"TXN-50001", "TXN-50002"} & two


def test_detection_metrics_are_believable_and_show_misses(store, candidates):
    flagged = {c.subject_id for c in candidates if c.score >= 50}
    rows = [{"flagged": g["subject_id"] in flagged, "is_fraud": bool(g["is_fraud"]), "story": g["story"]}
            for g in store.ground_truth()]
    m = detection_metrics(rows)
    print(m)
    assert 0.4 < m.precision < 0.99 and 0.4 < m.recall < 0.99
    assert m.misses_by_story.get("slow_bleed", 0) > 0
    assert m.false_positives > 0


def test_generation_is_repeatable():
    from demo.generator import generate
    assert generate(NOW).transactions == generate(NOW).transactions


def test_labels_are_not_reachable_from_tool_helpers(store):
    assert "is_fraud" not in str(store.get_transactions("ACC-10042"))


def test_login_pattern_is_found_across_mixed_timezone_offsets():
    data = {
        "accounts": [{"account_id": "A", "customer_id": "C", "name": "N", "address": "X", "portfolio": "p"}],
        "transactions": [],
        "loans": [],
        "logins": [
            {"login_id": f"L{i}", "account_id": "A", "customer_id": "C", "device_id": "D", "ip": "1",
             "timestamp": stamp, "outcome": outcome}
            for i, (stamp, outcome) in enumerate([
                ("2026-10-30T15:31:00+05:30", "failure"),   # 10:01 UTC
                ("2026-10-30T10:02:00+00:00", "failure"),
                ("2026-10-30T15:33:00+05:30", "failure"),
                ("2026-10-30T10:04:00+00:00", "success"),
            ])
        ],
    }
    assert any(c.category == "repeated_login_failures" for c in scan(data, load_config()))
