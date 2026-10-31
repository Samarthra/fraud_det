"""PROTOTYPE, throwaway. Exports real seeded records for the Typology logic. Run from backend/app."""
import json, sys
from collections import defaultdict
from datetime import datetime, timedelta
sys.path.insert(0, ".")
from demo.seed import load_sample
from detection.engine import load_config, scan
from evals.db_source import DbSource
from store import Store

T = lambda v: int(datetime.fromisoformat(v).timestamp())
store = Store(); load_sample(store); config = load_config()
data = store.detection_inputs()
source = DbSource()
held_out = {subject for subject, _, _ in source.held_out()}
acc = {a["account_id"]: a for a in data["accounts"]}
first_acc = {}
for a in data["accounts"]:
    first_acc.setdefault(a["customer_id"], a)
house = lambda a: (a["name"].split()[-1].lower() + "|" + a["address"])
seen = {}
for r in [*data["logins"], *data["transactions"]]:
    if r.get("device_id"):
        k = (r["account_id"], r["device_id"]); t = T(r["timestamp"]); seen[k] = min(seen.get(k, t), t)
payers = defaultdict(list)
for t in data["transactions"]:
    payers[t["beneficiary_id"]].append((T(t["timestamp"]), t["account_id"]))
out = {}
def blank(a):
    return {"id": a["account_id"], "c": a["customer_id"], "name": a["name"], "logins": [], "events": [], "pays": [], "payouts": []}
for a in data["accounts"]:
    out[a["account_id"]] = blank(a)
for l in data["logins"]:
    out[l["account_id"]]["logins"].append({"id": l["login_id"], "o": l["outcome"], "d": l["device_id"], "ip": l["ip"], "t": T(l["timestamp"])})
for e in data["events"]:
    out[e["account_id"]]["events"].append({"id": e["event_id"], "ty": e["type"], "t": T(e["at"]), "details": e["details"]})
paid = defaultdict(set)
for t in sorted(data["transactions"], key=lambda r: r["timestamp"]):
    aid, b, when = t["account_id"], t["beneficiary_id"], T(t["timestamp"])
    first = bool(paid[aid]) and b not in paid[aid]
    paid[aid].add(b)
    d = t.get("device_id"); s = seen.get((aid, d)); earliest = min(v for (x, _), v in seen.items() if x == aid) if s else None
    newd = bool(s and s > earliest and when - s <= 86400)
    if first or newd:
        out[aid]["pays"].append({"id": t["transaction_id"], "b": b, "amt": t["amount"], "d": d, "t": when, "first": first, "newd": newd,
                                 "payers7": len({x for w, x in payers[b] if 0 <= when - w <= 7 * 86400}),
                                 "payersAll": len({x for _, x in payers[b]})})
for l in data["loans"]:
    if l.get("disbursed_account_id"):
        out[l["disbursed_account_id"]]["payouts"].append({"id": l["application_id"], "amt": l["amount"], "t": T(l["disbursed_at"])})
claims = [{"id": c["claim_id"], "c": c["customer_id"], "d": c.get("device_id"), "ip": c.get("ip"), "ph": c.get("phone"), "t": T(c["timestamp"]),
           "hh": house(first_acc[c["customer_id"]]), "pf": sorted(store.customer_portfolios(c["customer_id"]))} for c in data["claims"]]
def view(a, cat=None):
    rec = next((r.data for r in a.supporting_records if r.kind == "transaction"), {})
    return {"id": a.id, "cat": a.category, "score": a.score, "acc": a.account_id, "rules": [h.rule for h in a.rule_hits], "txn": a.transaction_id, "b": rec.get("beneficiary_id"), "d": a.device_id, "t": T(a.created_at)}
cases = []
for p in ("portfolio-1", "portfolio-2"):
    for c in store.cases(p):
        cases.append({"id": c.id, "portfolio": p, "cat": c.category, "band": c.priority.band, "alerts": [view(a) for a in store.case_alerts(c.id)]})
labels = {g["subject_id"]: (bool(g["is_fraud"]), g["story"]) for g in store.ground_truth()}
sweep = []
actionable = config["thresholds"]["actionable"]
for c in scan(data, config):
    if c.subject_id in held_out or c.subject_id not in labels:
        continue
    if c.score < actionable and labels[c.subject_id][0]:
        continue  # fraud below the line never reaches an Investigation
    rec = next((r.data for r in c.records if r.kind == "transaction"), {})
    sweep.append({"subject": c.subject_id, "fraud": labels[c.subject_id][0], "story": labels[c.subject_id][1], "pf": acc[c.account_id]["portfolio"],
                  "alert": {"id": c.subject_id, "cat": c.category, "score": c.score, "acc": c.account_id, "rules": [h.rule for h in c.hits], "txn": c.transaction_id, "b": rec.get("beneficiary_id"), "d": c.device_id, "t": T(c.at)}})
used = {a["acc"] for c in cases for a in c["alerts"]} | {s["alert"]["acc"] for s in sweep}
world = {"accounts": {k: v for k, v in out.items() if k in used}, "claims": claims, "cases": cases, "sweep": sweep, "held_out_removed": len(held_out)}
json.dump(world, open(sys.argv[1], "w"), separators=(",", ":"))
print("cases", len(cases), "sweep", len(sweep), "accounts", len(world["accounts"]), "held out removed", len(held_out))
