# FraudLens AI - Simple Guide

## What this project does

FraudLens AI is a small web app that helps a bank find suspicious money activity.

Think of it like a detective:
- It reads bank records (customers, transactions, logins, loans).
- It looks for bad patterns (too many logins, new devices, strange transfers).
- It makes **Alerts**.
- A person (Analyst) looks at an Alert and decides what to do.

Nothing here is real bank data. It is all fake demo data.

## The two main parts

- `frontend/` - the website you see in the browser (React).
- `backend/` - the server that stores data and does the thinking (Python FastAPI).

## Where things are

- `frontend/src/pages/` - screens:
  - `Upload.tsx` - load CSV/Excel/JSON files or sample data.
  - `Dashboard.tsx` - numbers and Alerts.
  - `Cases.tsx` / `CasePage.tsx` - Alerts turned into Cases to investigate.
  - `Evaluations.tsx` - test results.
  - `Governance.tsx` - audit trail.
- `frontend/src/ui.tsx` - small reusable UI pieces (Card, Button, etc.).
- `backend/app/api/main.py` - web API (URLs the frontend calls).
- `backend/app/store.py` - database helpers.
- `backend/app/detection/engine.py` - finds suspicious patterns.
- `backend/app/agent/` - AI investigation agent.
- `backend/app/contracts.py` - shapes of data shared by frontend and backend.
- `docs/spec.md` - full technical spec.

## How to run it

Backend (from `backend/app`):
```
uv run uvicorn api.main:app --port 8010
```

Frontend (from `frontend`):
```
npm run dev
```

Then open http://localhost:5173

## Login

There are 2 dummy users:
- Username: `analyst-1`  Password: `password`
- Username: `analyst-2`  Password: `password`

Each user sees only their own portfolio's data.

## What happens on each screen

1. **Upload** - drop a file or load sample data. Bad rows are listed.
2. **Dashboard** - see counts, risk levels, categories, and Alerts. Click an Alert for details.
3. **Case queue** - Alerts become Cases. Open one to investigate.
4. **Investigation** - the AI reads evidence and writes a report. You make the final decision.
5. **Evaluations** - how well detection and the agent did.
6. **Governance** - audit log of actions.

## Simple words

- **Alert** = "this looks suspicious."
- **Case** = an Alert someone is working on.
- **Evidence** = records used to explain an Alert.
- **Decision** = final human choice (fraud / not fraud / escalate).
