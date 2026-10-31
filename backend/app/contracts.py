"""The shared contract: FastAPI response models and the Synthesis tool schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Product = Literal["core_banking", "lending"]
RiskLevel = Literal["low", "medium", "high"]
Assessment = Literal["suspicious", "not_suspicious"]
Action = Literal[
    "hold_transaction",
    "block_beneficiary",
    "contact_customer",
    "freeze_account",
    "escalate_to_compliance",
    "no_action",
]
DecisionValue = Literal[
    "requires_investigation", "false_positive", "confirmed_fraud", "escalated"
]
CaseStatus = Literal["new", "investigating", "report_ready", "decided"]
InvestigationStatus = Literal["running", "complete"]
VerificationStatus = Literal["verified", "unverified"]
EvidenceKind = Literal[
    "transaction",
    "account",
    "account_event",
    "device",
    "beneficiary",
    "alert",
    "relationship",
]
Stage = Literal["triage", "evidence", "synthesis", "verification", "report", "follow_up"]
StepType = Literal[
    "stage_started", "tool_call", "tool_result", "denied", "verification", "stage_finished"
]


class Analyst(BaseModel):
    id: str
    name: str
    portfolio: str


class AnalystScope(BaseModel):
    """Injected by code. Never sent to the model."""

    model_config = ConfigDict(frozen=True)

    analyst_id: str
    portfolio: str


class RuleHit(BaseModel):
    rule: str
    points: int
    reason: str


class SupportingRecord(BaseModel):
    kind: str
    source_ref: str
    data: dict[str, Any]


class Alert(BaseModel):
    id: str
    case_id: str | None  # null below the actionable threshold
    category: str
    product: Product
    risk_level: RiskLevel
    score: int = Field(ge=0, le=100)
    rule_hits: list[RuleHit]
    customer_id: str
    account_id: str
    transaction_id: str | None = None
    device_id: str | None = None
    application_id: str | None = None
    supporting_records: list[SupportingRecord]
    created_at: str


class Decision(BaseModel):
    decision: DecisionValue
    analyst: str
    note: str = ""
    at: str


class DecisionRequest(BaseModel):
    decision: DecisionValue
    note: str = ""


class Case(BaseModel):
    id: str
    alert_id: str
    customer_id: str
    account_id: str
    category: str
    risk_level: RiskLevel
    supporting_records: list[SupportingRecord]
    status: CaseStatus
    decisions: list[Decision]  # append-only, latest is current
    investigation_id: str | None = None


class Evidence(BaseModel):
    id: str
    investigation_id: str
    kind: EvidenceKind
    source_ref: str
    data: dict[str, Any]
    tool_call_id: str | None = None
    collected_at: str


class Finding(BaseModel):
    statement: str
    evidence_ids: list[str]


class ReportDraft(BaseModel):
    """The only thing the model fills in, through the forced Synthesis tool."""

    assessment: Assessment
    summary: str
    findings: list[Finding]
    limitations: list[str]
    recommended_actions: list[Action]


class FollowUpDraft(BaseModel):
    """Filled in through a forced tool, using existing Evidence only."""

    answer: str
    evidence_ids: list[str]


class Report(BaseModel):
    assessment: Assessment | None  # null only on an empty report
    summary: str
    findings: list[Finding]
    limitations: list[str]
    recommended_actions: list[Action]
    verification: VerificationStatus
    verification_errors: list[str] = []


class Step(BaseModel):
    seq: int
    stage: Stage
    type: StepType
    summary: str
    evidence_ids: list[str] = []
    at: str


class FollowUp(BaseModel):
    id: str
    question: str
    answer: str | None = None
    evidence_ids: list[str] = []
    verification: VerificationStatus | None = None
    asked_at: str


class FollowUpRequest(BaseModel):
    question: str


class Investigation(BaseModel):
    id: str
    case_id: str
    status: InvestigationStatus
    report: Report | None
    evidence: list[Evidence]
    follow_ups: list[FollowUp]
    trace_url: str | None = None
    is_replay: bool = False
    replay_captured_at: str | None = None


class CaseDetail(BaseModel):
    case: Case
    alert: Alert
    report: Report | None = None


class StartInvestigation(BaseModel):
    replay: bool = False


class InvestigationStarted(BaseModel):
    investigation_id: str


class RejectedRow(BaseModel):
    row: int  # file line for CSV and Excel, 1-based item for JSON
    reasons: list[str]


class UploadResult(BaseModel):
    dataset: str
    filename: str
    total_rows: int
    loaded: int
    rejected: list[RejectedRow]
    ignored_columns: list[str] = []
    blank_rows: int = 0
    alerts_created: int = 0


class Stats(BaseModel):
    records_processed: int
    flagged_events: int
    risk_distribution: dict[RiskLevel, int]
    fraud_categories: dict[str, int]


class DetectionMetrics(BaseModel):
    precision: float
    recall: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    misses_by_story: dict[str, int]


class ScenarioScore(BaseModel):
    name: str
    correct: int
    runs: int
    gate: int  # correct runs needed out of 10
    passed: bool


class EvalCaseResult(BaseModel):
    case_id: str
    group: str
    expected: Assessment
    assessment: Assessment | None
    verification: VerificationStatus | None
    failures: list[str]
    seconds: float
    trace_url: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures


class EvalRun(BaseModel):
    """`evals/results/latest.json`, served by GET /evals/latest."""

    run_at: str
    commit: str
    model: str
    estimated_cost_inr: float
    notice: str
    detection: DetectionMetrics | None
    scenarios: list[ScenarioScore]
    injection_passed: int
    injection_total: int
    denials_passed: int
    denials_total: int
    held_out_correct: int
    held_out_total: int
    failures: list[EvalCaseResult]
