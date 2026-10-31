"""Run from backend/app: uvicorn api.main:app --port 8010"""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from agent.graph import answer_followup, empty_report, run_investigation  # noqa: E402
from contracts import (  # noqa: E402
    Alert,
    Analyst,
    AnalystScope,
    Case,
    CaseDetail,
    Decision,
    DecisionRequest,
    FollowUp,
    FollowUpRequest,
    Investigation,
    InvestigationStarted,
    StartInvestigation,
    Stats,
    Step,
    SupportingRecord,
    UploadResult,
)
from demo import replay as replays  # noqa: E402
from demo.sample_files import bad_rows_csv  # noqa: E402
from demo.seed import load_sample  # noqa: E402
from detection.engine import load_config, run_detection  # noqa: E402
from ingest import DATASETS, FileRejected, check_file, template_csv  # noqa: E402
from store import Store, now  # noqa: E402

DB_PATH = os.environ.get("FRAUDLENS_DB", str(Path(__file__).resolve().parents[2] / "fraudlens.db"))
RESULTS = Path(__file__).resolve().parents[1] / "evals" / "results" / "latest.json"
PROGRESS = RESULTS.with_name("progress.json")
APP_DIR = Path(__file__).resolve().parents[1]
store = Store(DB_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI) -> Iterator[None]:
    for investigation_id in store.running_investigations():
        store.save_report(investigation_id, empty_report("The Investigation was interrupted."))
    for follow_up_id in store.pending_follow_ups():
        store.save_followup_answer(follow_up_id, "This answer was interrupted.", [], "unverified")
    yield


app = FastAPI(title="FraudLens AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


security = HTTPBasic(auto_error=False)


def current_scope(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> AnalystScope:
    analyst_id = store.authenticate(credentials.username, credentials.password) if credentials else None
    analyst = store.analyst(analyst_id)
    if analyst is None:
        raise HTTPException(401, "Sign in first.")
    return AnalystScope(analyst_id=analyst.id, portfolio=analyst.portfolio)


def visible_records(records: list[SupportingRecord], portfolio: str) -> list[SupportingRecord]:
    """A shared-device or loan Alert can name accounts from another Portfolio."""

    def allowed(record: SupportingRecord) -> bool:
        account = record.data.get("account_id")
        if account:
            return store.account_portfolio(account) == portfolio
        customer = record.data.get("customer_id")
        return not customer or portfolio in store.customer_portfolios(customer)

    return [r for r in records if allowed(r)]


def scoped(item, portfolio: str):
    records = visible_records(item.supporting_records, portfolio)
    return item.model_copy(update={"supporting_records": records})


def require_portfolio(account_id: str, scope: AnalystScope, target: str) -> None:
    if store.account_portfolio(account_id) != scope.portfolio:
        store.audit("access_denied", analyst_id=scope.analyst_id, target=target)
        raise HTTPException(403, f"{target} is outside this Analyst's Portfolio.")


def owned_case(case_id: str, scope: AnalystScope) -> Case:
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, "Case not found.")
    require_portfolio(case.account_id, scope, case_id)
    return case


def owned_investigation(investigation_id: str, scope: AnalystScope) -> Investigation:
    investigation = store.get_investigation(investigation_id)
    if investigation is None:
        raise HTTPException(404, "Investigation not found.")
    owned_case(investigation.case_id, scope)
    return investigation


@app.get("/analysts", response_model=list[Analyst])
def analysts():
    return store.analysts()


@app.get("/me", response_model=Analyst)
def me(scope: AnalystScope = Depends(current_scope)):
    analyst = store.analyst(scope.analyst_id)
    if analyst is None:
        raise HTTPException(404, "Analyst not found.")
    return analyst


@app.get("/users")
def users(scope: AnalystScope = Depends(current_scope)):
    return store.users()


@app.post("/ingest/{dataset}", response_model=UploadResult)
async def ingest(dataset: str, file: UploadFile, scope: AnalystScope = Depends(current_scope)):
    content = await file.read()
    try:
        rows, result = check_file(
            dataset,
            file.filename or "upload",
            content,
            store.known_ids(scope.portfolio),
            scope.portfolio,
        )
    except FileRejected as e:
        store.audit("file_rejected", analyst_id=scope.analyst_id, filename=file.filename, reason=str(e))
        raise HTTPException(422, str(e)) from e
    store.insert_rows(dataset, rows)
    result.alerts_created = run_detection(store)
    store.audit("file_uploaded", analyst_id=scope.analyst_id, filename=file.filename,
                dataset=dataset, loaded=result.loaded)
    if result.rejected:
        store.audit("rows_rejected", analyst_id=scope.analyst_id, filename=file.filename,
                    rows=[r.row for r in result.rejected])
    return result


@app.get("/ingest/templates/{dataset}", response_class=PlainTextResponse)
def template(dataset: str):
    if dataset not in DATASETS:
        raise HTTPException(404, "Unknown dataset.")
    return PlainTextResponse(
        template_csv(dataset),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={dataset}_template.csv"},
    )


@app.post("/demo/sample")
def sample(scope: AnalystScope = Depends(current_scope)):
    if store.known_ids(scope.portfolio)["account_id"]:
        return {"alerts_created": 0, "already_loaded": True}
    return {"alerts_created": load_sample(store), "already_loaded": False}


@app.get("/demo/sample-file", response_class=PlainTextResponse)
def sample_file():
    return PlainTextResponse(
        bad_rows_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_transactions_bad_rows.csv"},
    )


@app.post("/demo/reset")
def reset(scope: AnalystScope = Depends(current_scope)):
    """Clears demo data. The audit trail survives, and records who reset."""
    store.reset()
    created = load_sample(store)
    store.audit("demo_reset", analyst_id=scope.analyst_id)
    return {"alerts_created": created}


@app.post("/detection/rerun")
def rerun(scope: AnalystScope = Depends(current_scope)):
    created = run_detection(store)
    store.audit("detection_rerun", analyst_id=scope.analyst_id, alerts_created=created)
    return {"alerts_created": created}


@app.get("/detection/rules")
def detection_rules(scope: AnalystScope = Depends(current_scope)):
    """Read fresh each time, so the page always matches rules.yaml."""
    return load_config()


@app.get("/stats", response_model=Stats)
def stats(scope: AnalystScope = Depends(current_scope)):
    return store.stats(scope.portfolio)

@app.get("/graph")
def graph(account_id: str, scope: AnalystScope = Depends(current_scope)):
    require_portfolio(account_id, scope, account_id)
    return store.relationship_graph(account_id, scope.portfolio)


@app.get("/graph/node")
def graph_node(id: str, type: str, scope: AnalystScope = Depends(current_scope)):
    detail = store.graph_node_detail(id, type, scope.portfolio)
    if detail is None:
        store.audit("access_denied", analyst_id=scope.analyst_id, target=id)
        raise HTTPException(403, f"{id} is outside this Analyst's Portfolio.")
    return detail


@app.get("/alerts", response_model=list[Alert])
def alerts(
    customer: str | None = None,
    transaction: str | None = None,
    product: str | None = None,
    risk_level: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    detection_type: str | None = None,
    scope: AnalystScope = Depends(current_scope),
):
    def keep(a: Alert) -> bool:
        day = a.created_at[:10]
        return (
            (not customer or customer.lower() in a.customer_id.lower())
            and (not transaction or transaction.lower() in (a.transaction_id or "").lower())
            and (not product or a.product == product)
            and (not risk_level or a.risk_level == risk_level)
            and (not date_from or day >= date_from)
            and (not date_to or day <= date_to)
            and (not detection_type or detection_type == a.category
                 or detection_type in {h.rule for h in a.rule_hits})
        )

    return [scoped(a, scope.portfolio) for a in store.alerts(scope.portfolio) if keep(a)]


@app.get("/cases", response_model=list[Case])
def cases(scope: AnalystScope = Depends(current_scope)):
    return [scoped(c, scope.portfolio) for c in store.cases(scope.portfolio)]


@app.get("/cases/{case_id}", response_model=CaseDetail)
def case_detail(case_id: str, scope: AnalystScope = Depends(current_scope)):
    owned_case(case_id, scope)
    detail = store.case_detail(case_id)
    detail.replay_available = replays.replay_file(detail.alert.transaction_id) is not None
    detail.case = scoped(detail.case, scope.portfolio)
    detail.alert = scoped(detail.alert, scope.portfolio)
    return detail


@app.post("/cases/{case_id}/decision", response_model=Case)
def decide(case_id: str, body: DecisionRequest, scope: AnalystScope = Depends(current_scope)):
    case = owned_case(case_id, scope)
    report = store.get_report(case.investigation_id) if case.investigation_id else None
    if report and report.verification == "unverified" and not body.note.strip():
        raise HTTPException(422, "A note is required when the report is Unverified.")
    store.add_decision(
        case_id,
        Decision(decision=body.decision, analyst=scope.analyst_id, note=body.note, at=now()),
    )
    store.audit("decision_recorded", analyst_id=scope.analyst_id, case_id=case_id,
                decision=body.decision, note=body.note)
    return scoped(store.get_case(case_id), scope.portfolio)


@app.post("/cases/{case_id}/investigation", response_model=InvestigationStarted, status_code=202)
def investigate(
    case_id: str,
    background: BackgroundTasks,
    body: StartInvestigation | None = None,
    scope: AnalystScope = Depends(current_scope),
):
    case = owned_case(case_id, scope)
    replay = bool(body and body.replay)
    existing = store.get_investigation(case.investigation_id) if case.investigation_id else None
    if not replay:
        failed = existing and existing.report and existing.report.assessment is None
        if existing and not failed:
            return InvestigationStarted(investigation_id=existing.id)
        if failed:
            store.remove_investigation(existing.id)
            store.audit("investigation_replaced", analyst_id=scope.analyst_id, case_id=case_id,
                        replaced=existing.id)
        investigation_id = store.start_investigation(case_id)
        background.add_task(run_investigation, investigation_id, scope, store)
        return InvestigationStarted(investigation_id=investigation_id)

    path = replays.replay_file(store.get_alert(case.alert_id).transaction_id)
    if path is None:
        raise HTTPException(404, "No saved Replay for this Case.")
    if existing:
        if existing.status == "running":
            raise HTTPException(409, "An Investigation is still running.")
        if existing.report and existing.report.assessment is not None:
            return InvestigationStarted(investigation_id=existing.id)
        store.remove_investigation(existing.id)
        store.audit("investigation_replaced", analyst_id=scope.analyst_id, case_id=case_id,
                    replaced=existing.id)
    investigation_id = replays.load(store, case_id, path)
    store.audit("replay_started", analyst_id=scope.analyst_id, case_id=case_id,
                investigation_id=investigation_id)
    return InvestigationStarted(investigation_id=investigation_id)


@app.get("/investigations/{investigation_id}", response_model=Investigation)
def investigation(investigation_id: str, scope: AnalystScope = Depends(current_scope)):
    return owned_investigation(investigation_id, scope)


@app.get("/investigations/{investigation_id}/steps", response_model=list[Step])
def steps(investigation_id: str, after: int = 0, scope: AnalystScope = Depends(current_scope)):
    owned_investigation(investigation_id, scope)
    return store.steps(investigation_id, after)


@app.post("/investigations/{investigation_id}/followups", response_model=FollowUp, status_code=202)
def follow_up(
    investigation_id: str,
    body: FollowUpRequest,
    background: BackgroundTasks,
    scope: AnalystScope = Depends(current_scope),
):
    current = owned_investigation(investigation_id, scope)
    if current.is_replay:
        raise HTTPException(409, "Follow-ups are disabled during a Replay.")
    if current.status == "running" or any(f.answer is None for f in current.follow_ups):
        raise HTTPException(409, "Wait for the current answer to finish.")
    row = store.add_follow_up(investigation_id, body.question)
    background.add_task(answer_followup, investigation_id, row.id, scope, store)
    return row


@app.get("/evals/latest")
def evals_latest():
    if not RESULTS.exists():
        raise HTTPException(404, "No eval run has been saved yet.")
    return json.loads(RESULTS.read_text())


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def eval_running() -> bool:
    return subprocess.run(["pgrep", "-f", "evals[.]run"], capture_output=True).returncode == 0


@app.get("/evals/status")
def evals_status():
    try:
        progress = json.loads(PROGRESS.read_text())
    except (OSError, ValueError):
        progress = {}  # absent, or caught mid-write
    return {
        "running": eval_running(),
        "done": progress.get("done", 0),
        "total": progress.get("total", 0),
        "current": progress.get("current"),
        "last_error": progress.get("last_error"),
    }


@app.post("/evals/run", status_code=202)
def evals_run(scope: AnalystScope = Depends(current_scope)):
    """Separate process, so the run survives an API restart and never blocks a request."""
    if eval_running():
        raise HTTPException(409, "An eval run is already in progress.")
    PROGRESS.parent.mkdir(exist_ok=True)
    write_atomic(PROGRESS, json.dumps({"done": 0, "total": 0, "current": "starting"}))
    subprocess.Popen(
        [sys.executable, "-m", "evals.run"],
        cwd=APP_DIR,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    store.audit("eval_started", analyst_id=scope.analyst_id)
    return {"started": True}


@app.get("/audit")
def audit(scope: AnalystScope = Depends(current_scope)):
    rows = store.audit_trail(scope.portfolio)
    for row in rows:
        investigation_id = row["details"].get("investigation_id")
        row["trace_url"] = store.trace_url(investigation_id) if investigation_id else None
    return rows
