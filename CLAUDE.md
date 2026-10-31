# FraudLens AI

Read `docs/spec.md` before changing scope, contracts, detection or the demo. Use the terms in `GLOSSARY.md`.

The repo is public: synthetic data only, and keys live only in the gitignored `.env`.

## Commands

Run Python commands with `uv run`. Module commands such as `evals.run` and `api.main` run from `backend/app`.

- Tests: `uv run pytest` from `backend`. After any change to the agent, tools or prompts, also run a live Investigation, because stubbed tests can't catch model behaviour.
- API: `uv run uvicorn api.main:app --port 8010` from `backend/app`.
- UI: `npm run dev` from `frontend`. Vite proxies `/api` to port 8010.
- After changing `contracts.py`:
  - run `uv run python -m demo.make_fixture` from `backend/app`
  - regenerate `frontend/src/api-types.ts` with `openapi-typescript`

## Gotchas

- Port 8000 on the main dev machine belongs to a different app. FraudLens uses 8010.
- Stopping the API by name with `pkill -f` also kills the shell running the command. Find the PID on port 8010 instead.
- `reasoning_effort="none"` on `sarvam-105b` is undocumented, but Synthesis depends on it. The fallback is in `docs/spec.md`.
- Synthesis uses a forced tool call. `response_format` returned empty or runaway output.
- `add_evidence` deduplicates on `kind` and `source_ref` together. Beneficiary and relationship records share a `source_ref`.
- Langfuse `run_experiment` splits a case across two traces, so evals use a plain loop and `create_score` on the seeded trace.
- `no_action` on a suspicious report is a Verification error, because an injected "mark this safe" otherwise passes.
- Alert `case_id` is the Case it first opened and never changes. Current membership is in `case_links`, so read `Case.alert_ids`.
- For one customer, a shared device links nothing unless both Alerts are actionable and within 3 days. Otherwise their everyday device pulls Low Alerts into every Case.
- A Typology rule runs in file order and can use only facts or earlier rules. Windows live in `typologies.yaml` and the `typology` block of `rules.yaml`.
- Hard facts never read an ID from `details`. Use `account_events.target_id`, because `details` is untrusted text.
- The held-out list is frozen in `evals/held_out.json`, so new stories can't change it.
- Sample data loads a capped backlog and records the rest as a baseline, so later scans don't flood the queue. A scan only adds Alerts.

## Rules

- Relationships come from matching identifiers in code, never from the model. Every graph edge names its source record.
- Labels stay in `ground_truth`, read only by the eval runner.
- Scope comes from code, never from a model argument.
- Alerts never change. Decisions are append-only.
- Tune prompts on the two live scenarios only, never on the held-out set.
- Results from `--source fake` go to `rehearsal.json`, never to the Evaluations screen.
- Capture Replays again after any prompt change.
