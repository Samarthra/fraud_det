# FraudLens AI

An AI-assisted digital fraud investigation system: it raises suspicious activity, investigates it against verifiable evidence, and puts the result in front of a human analyst to decide.

## Language

**Alert**:
A signal raised by detection that activity on an account looks suspicious. An Alert is not a finding; it is a reason to look.
_Avoid_: Case, flag, incident

**Investigation**:
One agent run or conversation looking into a Case. It is optional, and always attaches exactly one report to that Case.
_Avoid_: Run, session, chat

**Case**:
The record opened for an actionable Alert, holding its evidence, status, Decision history and any Investigation report. It can hold several linked Alerts, and each Alert stays exactly as it was raised.
_Avoid_: Report, ticket, finding

**Lead Alert**:
The Alert a consolidated Case is built around, and the one an Investigation looks into.
_Avoid_: Primary Alert, parent

**Consolidation**:
Moving Alerts linked by a matching identifier into one Case. Code does it, never the model, and an Analyst can separate an Alert again.
_Avoid_: Merge, clustering

**Priority**:
A Case's rank in the queue, from its severity, financial exposure, related Alerts and confidence. A Case with one kind of signal is marked Needs review instead of ranking high.
_Avoid_: Risk level, score

**Assessment**:
The agent's conclusion in a Case on whether the activity is suspicious. It informs the Decision and never replaces it.
_Avoid_: Verdict, finding

**Decision**:
The Analyst's recorded outcome on a Case, which may change with its history kept. Recommended actions in a Case are not carried out by recording one.
_Avoid_: Verdict, resolution

**Recommendation**:
A Decision advising a temporary hold or enhanced verification. It is a record only and acts on nothing.
_Avoid_: Action, instruction

**Follow-up**:
A further analyst question within an existing Investigation, and its answer. It adds to the Investigation and never changes the Case.
_Avoid_: New investigation, re-run

**Analyst**:
The human who reviews a Case and records its decision.
_Avoid_: User, reviewer, operator

**Portfolio**:
The set of accounts an Analyst is allowed to see and investigate.
_Avoid_: Queue, book

**Evidence**:
A retrievable source record, or a result derived from source records, gathered during an Investigation, which a Case's claims cite by ID.
_Avoid_: Data, context, citation

**Verification**:
The deterministic check of a drafted Case against its Evidence and allowed actions. It proves that facts match, not that the reasoning is right.
_Avoid_: Validation, grounding, review

**Unverified**:
The status of an Investigation report that still failed Verification after its retry. The report is kept and shows the Analyst why it failed.
_Avoid_: Failed, invalid

**Replay**:
A labelled playback of a saved real Investigation, used when a live run isn't possible during the demo.
_Avoid_: Mock, simulation
