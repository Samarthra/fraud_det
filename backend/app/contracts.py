"""The shared contract: FastAPI response models and the Synthesis tool schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Product = Literal["core_banking", "lending", "insurance"]
RiskLevel = Literal["low", "medium", "high"]
PriorityBand = Literal["critical", "high", "medium", "low", "needs_review"]
Confidence = Literal["low", "medium", "high"]
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
    "requires_investigation",
    "false_positive",
    "confirmed_fraud",
    "escalated",
    "information_requested",
    "hold_recommended",
    "verification_recommended",
    "concluded",
]
EscalationTarget = Literal["fraud_specialist", "supervisor"]
CaseStatus = Literal["new", "investigating", "report_ready", "awaiting_information", "decided"]
LinkAction = Literal["grouped", "separated"]
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
    "typology",
    "login",
    "claim",
    "loan_application",
    "policy",
]
Stage = Literal[
    "triage", "evidence", "typology", "synthesis", "verification", "report", "follow_up"
]
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
    policy_id: str | None = None
    claim_id: str | None = None
    supporting_records: list[SupportingRecord]
    created_at: str


class Decision(BaseModel):
    decision: DecisionValue
    analyst: str
    note: str = ""
    at: str
    escalate_to: EscalationTarget | None = None


class DecisionRequest(BaseModel):
    decision: DecisionValue
    note: str = ""
    escalate_to: EscalationTarget | None = None


class LinkReason(BaseModel):
    """One matching identifier. A grouping with no reason can't exist."""

    kind: str  # account, customer, device, ip, phone or beneficiary
    value: str
    alert_ids: list[str]
    explanation: str


class CaseLink(BaseModel):
    """Append-only. The latest row for an Alert says which Case it sits in."""

    alert_id: str
    case_id: str
    action: LinkAction
    reasons: list[LinkReason] = []
    actor: str  # "correlation" or an Analyst ID
    note: str = ""
    at: str


class Priority(BaseModel):
    score: int = Field(ge=0, le=100)
    band: PriorityBand
    severity: int
    exposure: float  # INR, each sum of money counted once
    related_events: int
    confidence: Confidence
    needs_review: bool
    reasons: list[str]


class Note(BaseModel):
    text: str
    analyst: str
    at: str


class NoteRequest(BaseModel):
    text: str


class Classification(BaseModel):
    """An Analyst's change to a Case's risk. Alerts keep the original."""

    previous: RiskLevel
    risk_level: RiskLevel
    reason: str
    analyst: str
    at: str


class ClassificationRequest(BaseModel):
    risk_level: RiskLevel
    reason: str


class SeparateRequest(BaseModel):
    reason: str


class Case(BaseModel):
    id: str
    alert_id: str  # the lead Alert, which an Investigation looks into
    customer_id: str
    account_id: str
    category: str
    risk_level: RiskLevel  # the Analyst's latest classification, or original_risk_level
    original_risk_level: RiskLevel | None = None
    supporting_records: list[SupportingRecord]
    status: CaseStatus
    decisions: list[Decision]  # append-only, latest is current
    investigation_id: str | None = None
    alert_ids: list[str] = []
    products: list[Product] = []
    priority: Priority | None = None
    merged_into: str | None = None


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


class OtpFact(BaseModel):
    """Filled in through a forced tool. Code keeps it only if the quote is really in the record."""

    event_id: str
    otp_verified: bool
    quote: str


class OtpDraft(BaseModel):
    facts: list[OtpFact]


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


class TypologyStep(BaseModel):
    text: str
    record: str | None = None
    quote: str | None = None


class TypologyProof(BaseModel):
    typology: str
    name: str
    direction: Literal["fraud", "legitimate"]
    account: str
    subject: str
    steps: list[TypologyStep]
    evidence_id: str | None = None


class TypologyNear(BaseModel):
    typology: str
    name: str
    account: str
    missing: str


class TypologyResult(BaseModel):
    requirement: Literal["suspicious", "not_suspicious", "none"]
    proofs: list[TypologyProof]
    near: list[TypologyNear] = []


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
    typology: TypologyResult | None = None


class GraphNode(BaseModel):
    id: str
    type: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str
    evidence: str  # the source record and field that prove this edge


class CaseGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    out_of_scope_count: int = 0


class TimelineEvent(BaseModel):
    at: str
    system: Product
    kind: str
    source_ref: str
    summary: str


class HistoryEntry(BaseModel):
    at: str
    event: str
    actor: str
    summary: str


class CaseDetail(BaseModel):
    case: Case
    alert: Alert
    alerts: list[Alert] = []
    separated_alerts: list[Alert] = []  # taken out by an Analyst, kept here as evidence
    reasons: list[LinkReason] = []
    links: list[CaseLink] = []
    notes: list[Note] = []
    classifications: list[Classification] = []
    timeline: list[TimelineEvent] = []
    graph: CaseGraph | None = None
    history: list[HistoryEntry] = []
    report: Report | None = None
    replay_available: bool = False


class CaseReport(BaseModel):
    """The downloadable evidence file for one Case."""

    generated_at: str
    generated_by: str
    notice: str
    case: Case
    alerts: list[Alert]
    separated_alerts: list[Alert]
    grouping_reasons: list[LinkReason]
    links: list[CaseLink]
    relationships: CaseGraph
    timeline: list[TimelineEvent]
    notes: list[Note]
    classifications: list[Classification]
    investigation: "Investigation | None"
    typology: TypologyResult | None = None
    history: list[HistoryEntry]


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


class TypologyEval(BaseModel):
    """Before against after, and whether the check earned its place."""

    sweep: dict[str, Any]
    retries: int
    unverified_by_mismatch: int
    model_calls: int
    calls_per_investigation: float
    seconds_per_investigation: float
    reader: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    keep: bool | None = None  # null without a baseline to compare with
    keep_reasons: list[str] = []


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
    typology: TypologyEval | None = None
