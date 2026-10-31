# FraudLens AI

An AI-assisted digital fraud investigation system, built for the Azentio AI Hackathon on 31 October 2026.

FraudLens loads customer, transaction, login, loan and insurance data, flags suspicious activity with explainable rules, links related Alerts across those systems into one Case, and ranks Cases for an Analyst. An AI agent can investigate a Case and draft a report whose facts are checked in code. A human always makes the Decision.

All data is synthetic. This prototype demonstrates controls. It doesn't claim legal compliance or certification.

[![Watch the 23-second FraudLens AI launch video](docs/assets/fraudlens-launch.jpg)](docs/assets/fraudlens-launch.mp4)

**[Watch the 23-second video](docs/assets/fraudlens-launch.mp4)**, with sound.

## What it does

- **Upload:** CSV, Excel or JSON, with every invalid row listed and its reason given.
- **Detection:** configurable rules add up to a 0-100 score, covering suspicious transfers, shared devices, repeated login failures, suspicious loan applications, loan proceeds diversion and linked insurance claims.
- **Correlation:** Alerts sharing a real identifier become one Case, with the reason shown. An Analyst can separate any Alert, and the original Alerts never change.
- **Dashboard:** counts, risk distribution, fraud categories and six filters, with the reasons behind each Alert.
- **Case queue:** ranked by severity, financial exposure, related Alerts and confidence. A Case resting on one kind of signal is marked Needs review.
- **Case workspace:** risk assessment, timeline, relationship network, Alerts, notes and full evidence history, with a downloadable JSON report.
- **Analyst actions:** confirm, mark false positive, request information, escalate, recommend a hold or enhanced verification, record a conclusion, change the risk classification. Recommendations are never carried out.
- **Investigation:** a LangGraph agent chooses its own evidence tools, with live steps on screen and a Langfuse trace for each run.
- **Typology check:** code proves named fraud and legitimate patterns from a Case's records, with a proof citing each one, and the AI reads one fact from free text. It runs on every Investigation.
- **Verification:** code checks each amount, date and record ID against the cited Evidence, and holds the Assessment to any proof, so a report that fails is marked Unverified.
- **Access control:** each Analyst sees only their own Portfolio, enforced at the tool and API layers, and denials are audited.
- **Evals and Replay:** measured detection, scenario and prompt-injection results, plus a labelled playback of a saved real Investigation for when a live run isn't possible.

## Run it

You need [uv](https://docs.astral.sh/uv/) and Node.js. `uv` installs the right Python version itself.

**1. Add the keys**

```bash
cp .env.example .env
```

Fill in `SARVAM_API_KEY` and the two `LANGFUSE_*_KEY` values. Ask the team for these privately, and never commit `.env`. Upload, detection, the Dashboard and the Case queue all work without keys. Live Investigations need the Sarvam key, and traces need the Langfuse keys.

**2. Start the API**

```bash
cd backend
uv sync --python 3.13
cd app
uv run uvicorn api.main:app --port 8010
```

**3. Start the UI in a second terminal**

```bash
cd frontend
npm install
npm run dev
```

**4. Open http://localhost:5173**

Sign in with `analyst-1` or `analyst-2`, password `password`. These are public demo accounts, and this login is not real security. Then go to **Upload** and press **Load sample data**.

## Try the demo path

1. On **Upload**, download the file with bad rows, then upload it as `transactions` to see the rows rejected with reasons.
2. On **Dashboard**, filter by risk or detection type, then select an Alert to see why it was flagged.
3. In the **Transaction** filter, enter `TXN-50001`, select the Alert, and open its Case.
4. Press **Investigate**, watch the steps, then click a cited Evidence ID in the report.
5. Record a Decision, then see it on **Governance**.
6. Use `TXN-50002` for the false-positive scenario, or log out and sign in as the other Analyst to see access denied.
7. On **Case queue**, open the top Case, `TXN-50003`: six Alerts across lending, core banking and insurance. Read why they were grouped, click `DEV-9003` on **Network**, follow **Timeline**, separate an Alert, change the risk, recommend a hold and download the report.

Press **Reset demo** to start again. To try different detection settings, edit `backend/app/detection/rules.yaml`, then press **Re-run detection** on the Dashboard. A re-run only adds Alerts.

## Upload formats

Each dataset has fixed columns. Download a template from the Upload page. Load `customers` first, because the other datasets must link to existing accounts or customers. Dates must be ISO, such as `2026-10-31T16:21:00`.

## Tests and evals

```bash
cd backend
uv run pytest
```

Offline tests need no keys.

The eval suite uses the real model, takes about 25 minutes and spends about ₹12 of Sarvam credit:

```bash
cd backend/app
uv run python -m evals.run
```

It writes `evals/results/latest.json`, which the Evaluations screen shows, and compares the run with `evals/results/baseline.json`, the suite from before the Typology check. The saved `latest.json` predates that check, so run the suite to see its results.

## Find your way around

| Path | What's there |
|---|---|
| `docs/spec.md` | The full build spec: scope, contracts, rules, demo script |
| `GLOSSARY.md` | Domain terms |
| `backend/app/contracts.py` | Shared API and agent models |
| `backend/app/agent/` | The agent graph, prompts and Verification |
| `backend/app/tools/` | Evidence tools |
| `backend/app/detection/` | Rules and scoring |
| `backend/app/correlation/` | Consolidation, prioritisation, Case workspace |
| `backend/app/typology/` | Typology evaluator, facts and text reader. Rules are in `detection/typologies.yaml` |
| `backend/app/ingest/` | Upload parsing and validation |
| `backend/app/demo/` | Sample data, Replay |
| `backend/app/evals/` | Eval suite |
| `frontend/src/` | React screens |
| `replays/` | Saved real Investigations |

## Stack

React, Vite, Tailwind, FastAPI, LangGraph, SQLite, NetworkX, Sarvam `sarvam-105b` and Langfuse Cloud.
