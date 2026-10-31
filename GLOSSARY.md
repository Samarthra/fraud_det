# FraudLens AI

An AI-assisted digital fraud investigation system: it raises suspicious activity, investigates it against verifiable evidence, and puts the result in front of a human analyst to decide.

## Language

**Alert**:
A signal raised by detection that activity on an account looks suspicious. An Alert is not a finding; it is a reason to look.
_Avoid_: Case, flag, incident

**Investigation**:
One agent run or conversation looking into an account, transaction, or pattern. It may start from an Alert or from an analyst's prompt, and always produces exactly one Case.
_Avoid_: Run, session, chat

**Case**:
The reviewable report and analyst decision produced by one Investigation. A Case exists even when nothing suspicious is found.
_Avoid_: Report, ticket, finding

**Assessment**:
The agent's conclusion in a Case on whether the activity is suspicious. It informs the Decision and never replaces it.
_Avoid_: Verdict, finding

**Decision**:
The Analyst's recorded outcome on a Case. Recommended actions in a Case are not carried out by recording one.
_Avoid_: Verdict, resolution

**Follow-up**:
A further analyst question within an existing Investigation, and its answer. It adds to the Investigation and never changes the Case.
_Avoid_: New investigation, re-run

**Analyst**:
The human who reviews a Case and records its decision.
_Avoid_: User, reviewer, operator

**Evidence**:
A retrievable source record, or a result derived from source records, gathered during an Investigation, which a Case's claims cite by ID.
_Avoid_: Data, context, citation

**Verification**:
The deterministic check of a drafted Case against its Evidence and allowed actions. It proves that facts match, not that the reasoning is right.
_Avoid_: Validation, grounding, review

**Unverified**:
The status of a Case that still failed Verification after its retry. The Case is kept and shows the Analyst why it failed.
_Avoid_: Failed, invalid

**Replay**:
A labelled playback of a saved real Investigation, used when a live run isn't possible during the demo.
_Avoid_: Mock, simulation
