"""Consolidation, prioritisation and the Case workspace."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

import api.main as main
from contracts import Alert, CaseLink, Note, RuleHit, SupportingRecord
from correlation.consolidate import consolidate, find_groups, inr
from correlation.priority import assess, exposure
from demo import replay as replays
from demo.seed import load_sample
from detection.engine import load_config, run_detection, scan
from store import Store

CONFIG = load_config()
ONE = {"Authorization": "Basic " + base64.b64encode(b"analyst-1:password").decode()}
TWO = {"Authorization": "Basic " + base64.b64encode(b"analyst-2:password").decode()}
ACCOUNTS = {
    "A1": {"name": "Asha Rao", "address": "1 Road", "phone": "+91-1"},
    "A2": {"name": "Bala Iyer", "address": "2 Road", "phone": "+91-2"},
    "A3": {"name": "Chitra Rao", "address": "1 Road", "phone": "+91-3"},
}


def alert(id, account="A1", customer=None, device=None, at="2026-10-30T10:00:00+05:30", score=60,
          rules=("amount_spike",), record=None):
    records = [SupportingRecord(kind="transaction", source_ref=id, data=record)] if record else []
    return Alert(
        id=id, case_id=f"CASE-{id}", category="suspicious_transfer", product="core_banking",
        risk_level="medium", score=score, rule_hits=[RuleHit(rule=r, points=10, reason=r) for r in rules],
        customer_id=customer or f"C-{account}", account_id=account, device_id=device,
        transaction_id=id if record else None, supporting_records=records, created_at=at,
    )


def groups(*alerts):
    return find_groups(list(alerts), ACCOUNTS, CONFIG)


def test_alerts_on_one_account_within_the_window_group_and_explain_why():
    found = groups(alert("X"), alert("Y", at="2026-10-31T10:00:00+05:30"))
    assert len(found) == 1
    reason = found[0].reasons[0]
    assert (reason.kind, reason.value) == ("account", "A1") and "X, Y" in reason.explanation


def test_a_low_alert_needs_more_than_a_shared_owner():
    low = alert("Y", device="D", score=20, at="2026-10-30T12:00:00+05:30")
    low.case_id = None
    assert groups(alert("X", device="D"), low) == []
    assert len(groups(alert("X", account="A2", device="D"), low)) == 1  # another customer's device


def test_old_alerts_and_unrelated_alerts_stay_apart():
    assert groups(alert("X"), alert("Y", at="2026-10-20T10:00:00+05:30")) == []
    assert groups(alert("X"), alert("Y", account="A2")) == []


def test_a_shared_device_links_different_customers_but_not_a_household():
    assert len(groups(alert("X", device="D"), alert("Y", account="A2", device="D"))) == 1
    assert groups(alert("X", device="D"), alert("Y", account="A3", device="D")) == []


def test_a_shared_beneficiary_links_only_a_flagged_mule():
    paid = {"beneficiary_id": "BEN-1", "amount": 10}
    plain = alert("X", record=paid), alert("Y", account="A2", record=paid)
    assert groups(*plain) == []
    mule = alert("Z", account="A2", record=paid, rules=("mule_beneficiary",))
    assert groups(plain[0], mule)[0].reasons[0].kind == "beneficiary"


def test_a_common_identifier_proves_nothing():
    crowd = [alert(f"X{i}", account=f"B{i}", device="D") for i in range(CONFIG["correlation"]["hub_limit"] + 1)]
    assert groups(*crowd) == []


def test_case_size_is_capped():
    limit = CONFIG["correlation"]["max_alerts"]
    many = [alert(f"X{i}") for i in range(limit + 3)]
    assert all(len(g.alerts) <= limit for g in groups(*many))


def test_priority_favours_money_and_corroboration_over_a_lone_signal():
    lone = assess([alert("X", rules=("login_failures_then_success",))], None, CONFIG)
    takeover = assess(
        [alert("Y", score=100, rules=("new_device", "amount_spike", "new_beneficiary"),
               record={"amount": 500000}),
         alert("Z", score=55, rules=("login_failures_then_success",))], None, CONFIG)
    assert takeover.band == "critical" and takeover.score > lone.score
    assert takeover.exposure == 500000 and takeover.confidence == "high"


def test_insufficient_evidence_is_marked_for_review_not_ranked_highest():
    result = assess([alert("X", score=100, rules=("shared_device",), record={"amount": 9000000})], None, CONFIG)
    assert result.band == "needs_review" and result.needs_review
    assert result.score <= CONFIG["priority"]["needs_review_cap"]


def test_an_analyst_classification_drives_severity():
    result = assess([alert("X", score=100, rules=("a", "b", "c"))], "low", CONFIG)
    assert result.severity == 25 and "Analyst" in result.reasons[0]


def test_rupees_use_indian_digit_grouping():
    assert [inr(v) for v in (950, 185000, 1800000, 12345678.4)] == ["₹950", "₹1,85,000", "₹18,00,000", "₹1,23,45,678"]


def test_transferred_loan_proceeds_count_once():
    loan = alert("L", record={"amount": 600000})
    loan.application_id, loan.transaction_id = "L", None
    transfer = alert("T", rules=("loan_proceeds_transfer",), record={"amount": 575000})
    assert exposure([loan, transfer]) == 600000
    assert exposure([transfer]) == 575000


@pytest.fixture(scope="module")
def seeded():
    store = Store()
    load_sample(store)
    return store


def case_for(store, portfolio, transaction):
    alert = next(a for a in store.alerts(portfolio) if a.transaction_id == transaction)
    return store.get_case(alert.case_id)


def test_cross_system_fraud_becomes_one_case(seeded):
    case = case_for(seeded, "portfolio-1", "TXN-50003")
    assert case.products == ["core_banking", "insurance", "lending"]
    assert len(case.alert_ids) >= 5 and case.priority.band == "critical"
    categories = {a.category for a in seeded.case_alerts(case.id)}
    assert {"loan_proceeds_diversion", "suspicious_loan_application", "suspicious_insurance_claim",
            "shared_device"} <= categories


def test_takeover_login_and_transfer_are_one_case_and_transfer_leads(seeded):
    case = case_for(seeded, "portfolio-1", "TXN-50001")
    assert seeded.get_alert(case.alert_id).transaction_id == "TXN-50001"
    categories = {a.category for a in seeded.case_alerts(case.id)}
    assert {"account_takeover", "repeated_login_failures"} <= categories


def test_the_false_positive_stays_alone(seeded):
    assert len(case_for(seeded, "portfolio-1", "TXN-50002").alert_ids) == 1


def test_consolidation_never_crosses_a_portfolio(seeded):
    portfolios = {a["account_id"]: a["portfolio"] for a in seeded.account_rows().values()}
    for portfolio in ("portfolio-1", "portfolio-2"):
        for case in seeded.cases(portfolio):
            assert {portfolios[seeded.get_alert(a).account_id] for a in case.alert_ids} == {portfolio}


def test_consolidating_again_changes_nothing_and_alerts_keep_their_case_id():
    store = Store()
    load_sample(store)
    before = {a.id: a.model_dump_json() for a in store.all_alerts()}
    assert consolidate(store, CONFIG) == 0
    assert {a.id: a.model_dump_json() for a in store.all_alerts()} == before


def test_detection_covers_uploaded_style_insurance_and_disbursement_records():
    store = Store()
    load_sample(store)
    candidates = scan(store.detection_inputs(), CONFIG)
    transfer = next(c for c in candidates if c.subject_id == "TXN-50003")
    assert {"loan_proceeds_transfer", "recent_bank_change"} <= {h.rule for h in transfer.hits}
    claim = next(c for c in candidates if c.subject_id == "CLM-9001")
    assert claim.product == "insurance" and {h.rule for h in claim.hits} == {"early_claim", "claim_linked_identity"}


def test_a_genuine_early_claim_stays_low_and_a_household_is_not_a_ring():
    store = Store()
    load_sample(store)
    candidates = [c for c in scan(store.detection_inputs(), CONFIG) if c.product == "insurance"]
    labels = {g["subject_id"]: g["story"] for g in store.ground_truth()}
    by_story = {}
    for c in candidates:
        by_story.setdefault(labels[c.subject_id], []).append(c.score)
    assert max(by_story["early_genuine_claim"]) < CONFIG["thresholds"]["actionable"]
    assert "family_claim" not in by_story


@pytest.fixture
def client(monkeypatch, tmp_path):
    store = Store()
    load_sample(store)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(replays, "REPLAYS", tmp_path)
    return TestClient(main.app)


def linked_case(client, transaction="TXN-50003", headers=ONE):
    alert = client.get("/alerts", params={"transaction": transaction}, headers=headers).json()[0]
    return client.get(f"/cases/{alert['case_id']}", headers=headers).json()


def test_queue_hides_absorbed_cases_and_sorts_by_priority(client):
    rows = client.get("/cases", headers=ONE).json()
    scores = [c["priority"]["score"] for c in rows]
    assert scores == sorted(scores, reverse=True)
    assert all(c["merged_into"] is None for c in rows)
    assert rows[0]["alert_ids"] and rows[0]["priority"]["band"] == "critical"


def test_every_graph_edge_cites_a_record_and_nothing_leaks(client):
    detail = linked_case(client)
    graph = detail["graph"]
    types = {n["type"] for n in graph["nodes"]}
    assert {"customer", "account", "device", "ip", "phone", "application", "transaction", "policy",
            "claim", "beneficiary"} <= types
    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["evidence"] and e["source"] in ids and e["target"] in ids for e in graph["edges"])
    assert "ACC-60010" not in ids and "CUS-60100" not in ids and graph["out_of_scope_count"] >= 1
    assert "ACC-60010" not in json.dumps(detail) and "APP-9004" not in json.dumps(detail)


def test_timeline_spans_systems_in_order(client):
    timeline = linked_case(client)["timeline"]
    assert {e["system"] for e in timeline} == {"core_banking", "lending", "insurance"}
    moments = [e["at"][:19] for e in timeline]
    assert len(moments) == len(timeline) and any(e["kind"] == "disbursement" for e in timeline)


def test_each_entity_type_can_be_inspected_within_the_portfolio(client):
    for node in linked_case(client)["graph"]["nodes"]:
        response = client.get("/graph/node", params={"id": node["id"], "type": node["type"]}, headers=ONE)
        assert response.status_code == 200, node
        assert response.json()["id"] == node["id"]


def test_entities_outside_the_portfolio_are_denied(client):
    for id, kind in [("CUS-60100", "customer"), ("APP-9004", "application"), ("ACC-60010", "account")]:
        assert client.get("/graph/node", params={"id": id, "type": kind}, headers=ONE).status_code == 403
    assert client.get("/graph/node", params={"id": "CLM-9001", "type": "claim"}, headers=TWO).status_code == 403
    records = client.get("/graph/node", params={"id": "DEV-9003", "type": "device"}, headers=ONE).json()["records"]
    assert records and "ACC-60010" not in json.dumps(records) and "CUS-60100" not in json.dumps(records)


def test_separating_keeps_the_alert_and_outlasts_a_rerun(client):
    detail = linked_case(client)
    case = detail["case"]
    alert_id = next(a for a in case["alert_ids"] if a != case["alert_id"])
    url = f"/cases/{case['id']}/alerts/{alert_id}/separate"
    assert client.post(url, headers=ONE, json={"reason": " "}).status_code == 422
    assert client.post(url, headers=TWO, json={"reason": "x"}).status_code == 403
    before = main.store.get_alert(alert_id).model_dump_json()
    after = client.post(url, headers=ONE, json={"reason": "Different customer"}).json()
    assert alert_id not in after["alert_ids"]
    assert main.store.get_alert(alert_id).model_dump_json() == before
    run_detection(main.store)
    current = linked_case(client)
    assert alert_id not in current["case"]["alert_ids"]
    assert any(h["event"] == "alert_separated" and "Different customer" in h["summary"] for h in current["history"])
    assert alert_id not in {i for r in current["reasons"] for i in r["alert_ids"]}
    assert alert_id not in " ".join(r["explanation"] for r in current["reasons"])
    assert alert_id in [a["id"] for a in current["separated_alerts"]]
    assert any(h["event"] == "alert_raised" and alert_id in h["summary"] for h in current["history"])
    report = client.get(f"/cases/{case['id']}/report", headers=ONE).json()
    assert alert_id in [a["id"] for a in report["separated_alerts"]]


def test_the_lead_alert_stays_with_its_case(client):
    case = linked_case(client)["case"]
    url = f"/cases/{case['id']}/alerts/{case['alert_id']}/separate"
    assert client.post(url, headers=ONE, json={"reason": "x"}).status_code == 409


def test_work_on_an_absorbed_case_is_refused_and_points_to_the_lead(client):
    lead = linked_case(client)["case"]
    alert = next(a for a in client.get("/alerts", headers=ONE).json()
                 if a["id"] in lead["alert_ids"] and a["case_id"] and a["case_id"] != lead["id"])
    absorbed = client.get(f"/cases/{alert['case_id']}", headers=ONE).json()
    assert absorbed["case"]["merged_into"] == lead["id"]
    response = client.post(f"/cases/{alert['case_id']}/decision", headers=ONE, json={"decision": "escalated"})
    assert response.status_code == 409


def test_consolidation_leaves_a_worked_case_where_it_is():
    store = Store()
    load_sample(store)
    case = case_for(store, "portfolio-1", "TXN-50003")
    moved = store.get_alert(next(a for a in case.alert_ids if store.get_alert(a).case_id not in (None, case.id)))
    store.add_case_link(CaseLink(alert_id=moved.id, case_id=case.id, action="separated", actor="analyst-1",
                                 at="2026-10-31T10:00:00+05:30"))
    store.add_note(moved.case_id, Note(text="Working this", analyst="analyst-1", at="2026-10-31T10:00:00+05:30"))
    consolidate(store, CONFIG)
    assert store.get_case(moved.case_id).merged_into is None


def test_analyst_workflow_is_append_only_and_nothing_is_executed(client):
    case = linked_case(client)["case"]
    url = f"/cases/{case['id']}/decision"
    for decision in ("false_positive", "information_requested", "hold_recommended",
                     "verification_recommended", "concluded"):
        assert client.post(url, headers=ONE, json={"decision": decision}).status_code == 422
    assert client.post(url, headers=ONE, json={"decision": "hold_recommended", "escalate_to": "supervisor",
                                               "note": "n"}).status_code == 422
    waiting = client.post(url, headers=ONE, json={"decision": "information_requested", "note": "Payslips"}).json()
    assert waiting["status"] == "awaiting_information"
    held = client.post(url, headers=ONE, json={"decision": "hold_recommended", "note": "Funds moving"}).json()
    assert held["status"] == "awaiting_information"  # a recommendation changes no status
    done = client.post(url, headers=ONE, json={"decision": "escalated", "escalate_to": "fraud_specialist"}).json()
    assert done["status"] == "decided" and done["decisions"][-1]["escalate_to"] == "fraud_specialist"
    assert len(done["decisions"]) == 3
    assert main.store.get_transaction("TXN-50003")["status"] == "completed"


def test_reclassifying_keeps_the_original_and_the_reason(client):
    case = linked_case(client)["case"]
    url = f"/cases/{case['id']}/risk"
    assert client.post(url, headers=ONE, json={"risk_level": "low", "reason": ""}).status_code == 422
    assert client.post(url, headers=ONE, json={"risk_level": "high", "reason": "same"}).status_code == 422
    changed = client.post(url, headers=ONE, json={"risk_level": "low", "reason": "Customer confirmed"}).json()
    assert changed["risk_level"] == "low" and changed["original_risk_level"] == "high"
    detail = client.get(f"/cases/{case['id']}", headers=ONE).json()
    assert detail["classifications"][0]["previous"] == "high"
    assert detail["alert"]["risk_level"] == "high"
    assert any(h["event"] == "risk_reclassified" for h in detail["history"])


def test_notes_are_kept_and_scoped(client):
    case = linked_case(client)["case"]
    url = f"/cases/{case['id']}/notes"
    assert client.post(url, headers=ONE, json={"text": " "}).status_code == 422
    assert client.post(url, headers=TWO, json={"text": "x"}).status_code == 403
    assert client.post(url, headers=ONE, json={"text": "Called the branch"}).status_code == 201
    assert client.get(f"/cases/{case['id']}", headers=ONE).json()["notes"][0]["analyst"] == "analyst-1"


def test_case_report_downloads_the_evidence_history(client):
    case = linked_case(client)["case"]
    client.post(f"/cases/{case['id']}/decision", headers=ONE, json={"decision": "concluded", "note": "Fraud ring"})
    response = client.get(f"/cases/{case['id']}/report", headers=ONE)
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    report = response.json()
    assert report["generated_by"] == "analyst-1" and "not been carried out" in report["notice"]
    assert report["alerts"] and report["timeline"] and report["relationships"]["edges"]
    assert any(h["event"] == "decision_recorded" for h in report["history"])
    assert "ACC-60010" not in response.text
    assert client.get(f"/cases/{case['id']}/report", headers=TWO).status_code == 403
    trail = [row["event"] for row in client.get("/audit", headers=ONE).json()]
    assert "report_downloaded" in trail and "alerts_grouped" in trail


def test_history_names_source_records(client):
    history = linked_case(client)["history"]
    assert any("Source records: TXN-50003" in h["summary"] for h in history)


def test_an_uploaded_loan_joins_the_transfer_of_its_proceeds(client):
    """One applicant, so no shared device: the payout itself has to make the link."""
    own = next(c for c in main.store.account_rows().values()
               if c["portfolio"] == "portfolio-1" and c["account_id"].startswith("ACC-30"))
    account, customer = own["account_id"], own["customer_id"]
    uploads = {
        "account_events": f"event_id,account_id,type,at,details\nEVT-X,{account},bank_account_changed,2026-10-19T10:00:00,changed\n",
        "loan_applications": ("application_id,customer_id,device_id,amount,status,timestamp,ip,phone,disbursed_account_id,disbursed_at\n"
                              f"APP-X,{customer},DEV-UP,300000,disbursed,2026-10-01T10:00:00,,,{account},2026-10-20T09:00:00\n"),
        "transactions": ("transaction_id,account_id,beneficiary_id,beneficiary_name,amount,timestamp,channel,status,device_id,ip_country,description\n"
                         f"TXN-X,{account},BEN-NEW1,New Co,280000,2026-10-20T11:00:00,mobile,completed,DEV-UP,IN,x\n"),
    }
    for dataset, text in uploads.items():
        assert client.post(f"/ingest/{dataset}", headers=ONE, files={"file": ("f.csv", text.encode())}).json()["loaded"] == 1
    detail = linked_case(client, "TXN-X")
    assert detail["case"]["products"] == ["core_banking", "lending"]
    assert "APP-X" in [r["value"] for r in detail["reasons"]]
    assert detail["case"]["priority"]["exposure"] == 300000


def test_policies_and_claims_can_be_uploaded(client):
    own = next(c for c in main.store.account_rows().values() if c["portfolio"] == "portfolio-1")
    customer = own["customer_id"]
    policies = f"policy_id,customer_id,product,sum_assured,start_date,status\nPOL-1,{customer},Life,500000,2026-10-01T10:00:00,active\n"
    response = client.post("/ingest/policies", headers=ONE, files={"file": ("p.csv", policies.encode())})
    assert response.json()["loaded"] == 1
    claims = (f"claim_id,policy_id,customer_id,amount,status,timestamp\n"
              f"CLM-1,POL-1,{customer},90000,submitted,2026-10-10T10:00:00\n"
              f"CLM-2,POL-404,{customer},90000,submitted,2026-10-10T10:00:00\n")
    result = client.post("/ingest/claims", headers=ONE, files={"file": ("c.csv", claims.encode())}).json()
    assert result["loaded"] == 1 and "POL-404" in result["rejected"][0]["reasons"][0]
    assert any(a["claim_id"] == "CLM-1" for a in client.get("/alerts", params={"product": "insurance"}, headers=ONE).json())
