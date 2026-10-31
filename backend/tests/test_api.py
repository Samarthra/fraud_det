import base64
import io

import pytest
from fastapi.testclient import TestClient

import api.main as main
from agent.graph import empty_report
from contracts import Finding, Report
from demo import replay as replays
from demo.sample_files import bad_rows_csv
from demo.seed import load_sample
from store import Store

def basic(user, password="password"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


ONE = basic("analyst-1")
TWO = basic("analyst-2")


def fake_run(investigation_id, scope, store):
    store.append_step(investigation_id, "triage", "stage_started", "Reading the Alert")
    evidence = store.add_evidence(investigation_id, "alert", "A", {"amount": 5})
    store.save_report(investigation_id, Report(
        assessment="suspicious", summary="s", limitations=[], recommended_actions=["hold_transaction"],
        verification="verified", findings=[Finding(statement="x", evidence_ids=[evidence.id])]))


@pytest.fixture(scope="module")
def seeded():
    store = Store()
    load_sample(store)
    return store


@pytest.fixture
def client(monkeypatch, tmp_path):
    store = Store()
    load_sample(store)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "run_investigation", fake_run)
    monkeypatch.setattr(main, "RESULTS", tmp_path / "latest.json")
    monkeypatch.setattr(replays, "REPLAYS", tmp_path)
    return TestClient(main.app)


def takeover(client, headers=ONE):
    alerts = client.get("/alerts", params={"transaction": "TXN-50001"}, headers=headers).json()
    return alerts[0]


def test_no_analyst_is_rejected(client):
    assert client.get("/alerts").status_code == 401


def test_stats_and_filters(client):
    stats = client.get("/stats", headers=ONE).json()
    assert stats["records_processed"] > 6000 and stats["flagged_events"] > 0
    assert sum(stats["risk_distribution"].values()) == stats["flagged_events"]
    for params, check in [
        ({"risk_level": "high"}, lambda a: a["risk_level"] == "high"),
        ({"product": "lending"}, lambda a: a["product"] == "lending"),
        ({"detection_type": "shared_device"}, lambda a: a["category"] == "shared_device"),
        ({"detection_type": "new_device"}, lambda a: "new_device" in [h["rule"] for h in a["rule_hits"]]),
    ]:
        rows = client.get("/alerts", params=params, headers=ONE).json()
        assert rows and all(check(a) for a in rows)
    assert client.get("/alerts", params={"date_to": "2000-01-01"}, headers=ONE).json() == []


def test_portfolio_scope_on_every_case_route(client):
    case_id = takeover(client)["case_id"]
    investigation = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    assert all(a["transaction_id"] != "TXN-50001" for a in client.get("/alerts", headers=TWO).json())
    for method, path, body in [
        ("get", f"/cases/{case_id}", None),
        ("post", f"/cases/{case_id}/decision", {"decision": "escalated"}),
        ("post", f"/cases/{case_id}/investigation", None),
        ("get", f"/investigations/{investigation}", None),
        ("get", f"/investigations/{investigation}/steps", None),
        ("post", f"/investigations/{investigation}/followups", {"question": "q"}),
    ]:
        assert client.request(method, path, headers=TWO, json=body).status_code == 403, path
    denied = [e for e in client.get("/audit", headers=TWO).json() if e["event"] == "access_denied"]
    assert len(denied) == 6


def test_upload_reports_bad_rows_and_detects(client):
    csv = bad_rows_csv().encode()
    res = client.post("/ingest/transactions", headers=ONE,
                      files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")}).json()
    assert res["total_rows"] == 12 and res["loaded"] == 8
    assert [r["row"] for r in res["rejected"]] == [10, 11, 12, 13]
    events = [e["event"] for e in client.get("/audit", headers=ONE).json()]
    assert "file_uploaded" in events and "rows_rejected" in events


def test_unusable_file_gets_a_clear_error(client):
    res = client.post("/ingest/transactions", headers=ONE,
                      files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")})
    assert res.status_code == 422 and "Missing required column" in res.json()["detail"]


def test_templates(client):
    assert "transaction_id" in client.get("/ingest/templates/transactions").text
    assert client.get("/ingest/templates/nope").status_code == 404


def test_decisions_keep_history_and_the_alert_never_changes(client):
    alert = takeover(client)
    case_id = alert["case_id"]
    client.post(f"/cases/{case_id}/decision", headers=ONE, json={"decision": "requires_investigation"})
    case = client.post(f"/cases/{case_id}/decision", headers=ONE,
                       json={"decision": "false_positive", "note": "explained"}).json()
    assert [d["decision"] for d in case["decisions"]] == ["requires_investigation", "false_positive"]
    assert case["status"] == "decided"
    assert takeover(client) == alert


def test_unverified_report_needs_a_note(client):
    case_id = takeover(client)["case_id"]
    inv = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    main.store.save_report(inv, empty_report("failed"))
    url = f"/cases/{case_id}/decision"
    assert client.post(url, headers=ONE, json={"decision": "escalated"}).status_code == 422
    assert client.post(url, headers=ONE, json={"decision": "escalated", "note": "n"}).status_code == 200


def test_investigation_flow_and_repeat_post(client):
    case_id = takeover(client)["case_id"]
    first = client.post(f"/cases/{case_id}/investigation", headers=ONE)
    assert first.status_code == 202
    inv = first.json()["investigation_id"]
    assert client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"] == inv
    body = client.get(f"/investigations/{inv}", headers=ONE).json()
    assert body["status"] == "complete" and body["report"]["assessment"] == "suspicious"
    assert len(client.get(f"/investigations/{inv}/steps", headers=ONE).json()) == 1
    assert client.get(f"/investigations/{inv}/steps", params={"after": 1}, headers=ONE).json() == []
    assert client.get(f"/cases/{case_id}", headers=ONE).json()["case"]["status"] == "report_ready"


def test_interrupted_runs_close_on_startup(client):
    case_id = takeover(client)["case_id"]
    inv = main.store.start_investigation(case_id)
    with TestClient(main.app):
        pass
    report = main.store.get_report(inv)
    assert report.assessment is None and "interrupted" in report.limitations[0]


def test_replay_capture_load_label_and_replacement(client):
    case_id = takeover(client)["case_id"]
    inv = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    replays.export(main.store, inv, "account_takeover")
    assert client.get(f"/cases/{case_id}", headers=ONE).json()["replay_available"]

    main.store.save_report(inv, empty_report("Sarvam returned 402"))
    new = client.post(f"/cases/{case_id}/investigation", headers=ONE, json={"replay": True}).json()["investigation_id"]
    assert new != inv
    body = client.get(f"/investigations/{new}", headers=ONE).json()
    assert body["is_replay"] and body["replay_captured_at"] and body["report"]["assessment"] == "suspicious"
    assert len(client.get(f"/investigations/{new}/steps", headers=ONE).json()) == 1
    assert client.post(f"/investigations/{new}/followups", headers=ONE, json={"question": "q"}).status_code == 409
    assert client.post(f"/cases/{case_id}/decision", headers=ONE, json={"decision": "escalated"}).status_code == 200
    events = [e["event"] for e in client.get("/audit", headers=ONE).json()]
    assert "replay_started" in events and "investigation_replaced" in events


def test_replay_is_blocked_while_running_and_missing_file_is_404(client):
    case_id = takeover(client)["case_id"]
    assert client.post(f"/cases/{case_id}/investigation", headers=ONE, json={"replay": True}).status_code == 404
    inv = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    replays.export(main.store, inv, "account_takeover")
    main.store._run("UPDATE investigations SET status='running' WHERE id=?", inv)
    assert client.post(f"/cases/{case_id}/investigation", headers=ONE, json={"replay": True}).status_code == 409


def test_shift_moves_timestamps_but_not_other_text():
    from datetime import timedelta
    out = replays.shift({"at": "2026-10-31T10:00:00+05:30", "note": "2026-10-31", "n": 5}, timedelta(hours=1))
    assert out == {"at": "2026-10-31T11:00:00+05:30", "note": "2026-10-31", "n": 5}


def test_upload_after_sample_does_not_flood_the_queue(client):
    res = client.post("/ingest/transactions", headers=ONE,
                      files={"file": ("b.csv", io.BytesIO(bad_rows_csv().encode()), "text/csv")}).json()
    assert res["alerts_created"] < 20


def test_lowering_a_rule_threshold_adds_alerts_on_rerun(client, monkeypatch):
    from detection import engine
    config = engine.load_config()
    config["rules"]["amount_spike"]["multiplier"] = 2
    monkeypatch.setattr(engine, "load_config", lambda: config)
    assert client.post("/detection/rerun", headers=ONE).json()["alerts_created"] > 0


def test_rerun_adds_alerts_and_leaves_existing_ones(client):
    before = {a["id"]: a for a in client.get("/alerts", headers=ONE).json()}
    client.post("/detection/rerun", headers=ONE)
    after = {a["id"]: a for a in client.get("/alerts", headers=ONE).json()}
    assert all(after[k] == v for k, v in before.items())


def test_evals_endpoint(client):
    assert client.get("/evals/latest").status_code == 404
    main.RESULTS.write_text('{"commit": "abc"}')
    assert client.get("/evals/latest").json()["commit"] == "abc"


def test_eval_starts_once_and_reports_progress(client, monkeypatch):
    started = []
    running = [False]
    monkeypatch.setattr(main, "PROGRESS", main.RESULTS.with_name("progress.json"))
    monkeypatch.setattr(main, "eval_running", lambda: running[0])
    monkeypatch.setattr(main.subprocess, "Popen", lambda *a, **k: started.append(a[0]))
    assert client.get("/evals/status").json()["running"] is False
    assert client.post("/evals/run").status_code == 401
    assert client.post("/evals/run", headers=ONE).status_code == 202
    assert started[0][1:] == ["-m", "evals.run"]
    running[0] = True
    assert client.post("/evals/run", headers=ONE).status_code == 409
    assert len(started) == 1
    assert client.get("/evals/status").json()["current"] == "starting"
    assert "eval_started" in [e["event"] for e in client.get("/audit", headers=ONE).json()]


def test_sample_loads_once_and_reset_reseeds(client):
    assert client.post("/demo/sample", headers=ONE).json()["already_loaded"]
    assert client.post("/demo/reset", headers=ONE).json()["alerts_created"] > 0
    assert client.get("/analysts").json()[0]["id"] == "analyst-1"


def test_eval_source_uses_real_data():
    from evals.db_source import DbSource
    source = DbSource()
    held = source.held_out()
    assert len(held) >= 10 and {w for _, _, w in held} == {"suspicious", "not_suspicious"}
    assert source.detection().precision > 0.5
    assert source.scenario("account_takeover").get_alert_for_investigation("EVAL-1").transaction_id == "TXN-50001"
    store = source.poisoned("description", "payload")
    assert store.get_transactions("ACC-10042")[0]["description"] == "payload"


def test_investigation_ids_stay_unique_across_resets():
    store = Store()
    load_sample(store)
    case_id = store.alerts("portfolio-1")[0].case_id or store.cases("portfolio-1")[0].id
    first = store.start_investigation(case_id)
    store.reset()
    load_sample(store)
    assert store.start_investigation(store.cases("portfolio-1")[0].id) != first


def test_audit_is_scoped_to_the_analysts_portfolio(client):
    case_id = takeover(client)["case_id"]
    client.post(f"/cases/{case_id}/decision", headers=ONE, json={"decision": "escalated", "note": "private note"})
    client.post(f"/cases/{case_id}/investigation", headers=ONE)
    assert "private note" in str(client.get("/audit", headers=ONE).json())
    other = str(client.get("/audit", headers=TWO).json())
    assert "private note" not in other and case_id not in other and "tool_call" not in other


def test_upload_cannot_touch_another_portfolio(client):
    account = main.store._one("SELECT account_id FROM accounts WHERE portfolio='portfolio-1'")["account_id"]
    head = "transaction_id,account_id,beneficiary_id,beneficiary_name,amount,timestamp,channel,status"
    row = f"TXN-77777,{account},BEN-1,X,500,2026-10-30,web,completed"
    res = client.post("/ingest/transactions", headers=TWO, files={"file": ("b.csv", io.BytesIO(f"{head}\n{row}".encode()), "text/csv")}).json()
    assert res["loaded"] == 0 and "Unknown account_id" in res["rejected"][0]["reasons"][0]


def test_reset_needs_an_analyst_and_keeps_the_audit_trail(client):
    assert client.post("/demo/reset").status_code == 401
    assert client.post("/demo/sample").status_code == 401
    case_id = takeover(client)["case_id"]
    client.post(f"/cases/{case_id}/decision", headers=ONE, json={"decision": "escalated"})
    client.post("/demo/reset", headers=ONE)
    events = [e["event"] for e in client.get("/audit", headers=ONE).json()]
    assert "decision_recorded" in events and "demo_reset" in events


def test_graph_shows_one_account_and_counts_other_portfolios(client):
    assert client.get("/graph", params={"account_id": "ACC-10042"}).status_code == 401
    assert client.get("/graph", params={"account_id": "ACC-10042"}, headers=TWO).status_code == 403
    body = client.get("/graph", params={"account_id": "ACC-10042"}, headers=ONE)
    graph = body.json()
    ids = {n["id"] for n in graph["nodes"]}
    assert {"ACC-10042", "DEV-9001", "BEN-7001", "ACC-10311"} <= ids
    assert graph["out_of_scope_count"] == 3 and "ACC-60001" not in body.text
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
    assert len(graph["nodes"]) < 40


def test_only_real_credentials_get_in(client):
    assert client.get("/stats", headers={"X-Analyst-Id": "analyst-1"}).status_code == 401
    for user, password in [("analyst-1", "demo"), ("analyst-1", "123456"), ("user1", "user1"), ("analyst-1", "wrong")]:
        assert client.get("/stats", headers=basic(user, password)).status_code == 401
    assert client.get("/users").status_code == 401
    assert client.get("/stats", headers=ONE).status_code == 200


def test_shared_device_records_from_another_portfolio_are_hidden(client):
    from contracts import Alert, RuleHit, SupportingRecord
    alert = Alert(id="ALT-X", case_id="CASE-X", category="shared_device", product="core_banking",
                  risk_level="high", score=80, rule_hits=[RuleHit(rule="shared_device", points=55, reason="r")],
                  customer_id="CUS-10420", account_id="ACC-10042",
                  supporting_records=[
                      SupportingRecord(kind="account", source_ref="ACC-10042", data={"account_id": "ACC-10042"}),
                      SupportingRecord(kind="account", source_ref="ACC-60001", data={"account_id": "ACC-60001", "name": "Secret"}),
                  ], created_at="2026-10-31T10:00:00+05:30")
    main.store.add_alert("x", alert)
    main.store.add_case(alert)
    rows = [client.get("/cases/CASE-X", headers=ONE).text,
            client.get("/alerts", params={"detection_type": "shared_device"}, headers=ONE).text,
            client.get("/cases", headers=ONE).text]
    for text in rows:
        assert "Secret" not in text and "ACC-60001" not in text
    assert "ACC-10042" in rows[0]


def test_a_failed_investigation_can_be_restarted(client):
    case_id = takeover(client)["case_id"]
    first = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    main.store.save_report(first, empty_report("Sarvam returned 402"))
    second = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    assert second != first
    assert client.get(f"/investigations/{second}", headers=ONE).json()["report"]["assessment"] == "suspicious"
    assert "investigation_replaced" in [e["event"] for e in client.get("/audit", headers=ONE).json()]


def test_interrupted_follow_ups_close_on_startup(client):
    case_id = takeover(client)["case_id"]
    inv = client.post(f"/cases/{case_id}/investigation", headers=ONE).json()["investigation_id"]
    main.store.add_follow_up(inv, "Stuck?")
    with TestClient(main.app):
        pass
    body = client.get(f"/investigations/{inv}", headers=ONE).json()
    assert body["follow_ups"][0]["verification"] == "unverified" and "interrupted" in body["follow_ups"][0]["answer"]


def test_half_written_eval_progress_is_not_an_error(client, monkeypatch):
    progress = main.RESULTS.with_name("progress.json")
    monkeypatch.setattr(main, "PROGRESS", progress)
    monkeypatch.setattr(main, "eval_running", lambda: True)
    progress.write_text('{"done": 3, "to')
    res = client.get("/evals/status")
    assert res.status_code == 200 and res.json()["running"] is True
