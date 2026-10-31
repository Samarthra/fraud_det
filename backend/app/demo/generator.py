"""Fixed-seed synthetic data. Labels come from stories, never from the rules."""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

SEED = 42
IST = timezone(timedelta(hours=5, minutes=30))
FIRST = "Aarav Diya Ishaan Kavya Rohan Meera Vikram Nisha Arjun Tara Kabir Anaya Dev Leela Neil Sana Yash Pooja Karan Isha".split()
LAST = "Sharma Verma Patel Reddy Nair Gupta Joshi Kulkarni Bose Das Khan Singh Pillai Shetty Malhotra Bhat".split()
CITIES = "Pune Mumbai Bengaluru Chennai Hyderabad Delhi Kochi Jaipur".split()
PAYEES = "Grocer Pharmacy Electricity Mobile_Recharge Broadband School_Fees Insurance Fuel Dining Rent".split()


@dataclass
class Sample:
    customers: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    logins: list[dict[str, Any]] = field(default_factory=list)
    loan_applications: list[dict[str, Any]] = field(default_factory=list)
    account_events: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    ground_truth: list[dict[str, Any]] = field(default_factory=list)


class Builder:
    def __init__(self, now: datetime):
        self.r = random.Random(SEED)
        self.now = now
        self.s = Sample()
        self.txn = 10000
        self.login = 10000
        self.loan = 1000
        self.policy_no = 2000
        self.claim_no = 2000

    def at(self, days_ago: float, minutes: float = 0) -> str:
        return (self.now - timedelta(days=days_ago, minutes=minutes)).isoformat(timespec="seconds")

    def daytime(self, days_ago: float) -> str:
        moment = (self.now - timedelta(days=days_ago)).replace(
            hour=self.r.randint(8, 21), minute=self.r.randint(0, 59), second=0, microsecond=0
        )
        return min(moment, self.now - timedelta(minutes=30)).isoformat(timespec="seconds")

    def account(self, account_id, customer_id, name, city, portfolio, years=None, address=None):
        slug = name.lower().replace(" ", ".")
        row = {
            "account_id": account_id,
            "customer_id": customer_id,
            "name": name,
            "phone": f"+91-90000-{int(customer_id[-5:].replace('-', '0')):05d}",
            "email": f"{slug}.{customer_id.lower()}@example.test",
            "address": address or f"{self.r.randint(1, 400)} Example Road, {city}",
            "onboarded_at": self.at(365 * (years or self.r.uniform(1, 6))),
            "portfolio": portfolio,
            "city": city,
        }
        self.s.customers.append(row)
        return row

    def pay(self, account, beneficiary_id, name, amount, timestamp, device, *, country="IN",
            description="", story=None, fraud=None, txn_id=None):
        if txn_id is None:
            self.txn += 1
            txn_id = f"TXN-{self.txn}"
        self.s.transactions.append({
            "transaction_id": txn_id, "account_id": account["account_id"],
            "beneficiary_id": beneficiary_id, "beneficiary_name": name, "amount": round(amount, 2),
            "timestamp": timestamp, "channel": "mobile", "status": "completed", "device_id": device,
            "ip_country": country, "description": description,
        })
        self.label(txn_id, bool(fraud), story or "normal")
        return txn_id

    def sign_in(self, account, device, timestamp, outcome="success", ip=None):
        self.login += 1
        self.s.logins.append({
            "login_id": f"LOG-{self.login}", "account_id": account["account_id"],
            "customer_id": account["customer_id"], "device_id": device,
            "ip": ip or f"10.0.{self.r.randint(0, 255)}.{self.r.randint(1, 254)}",
            "timestamp": timestamp, "outcome": outcome,
        })

    def apply(self, customer_id, device, amount, timestamp, story, fraud, *, application_id=None,
              status="submitted", ip=None, phone=None, disbursed_account_id=None, disbursed_at=None):
        if application_id is None:
            self.loan += 1
            application_id = f"APP-{self.loan}"
        self.s.loan_applications.append({
            "application_id": application_id, "customer_id": customer_id, "device_id": device,
            "amount": amount, "status": status, "timestamp": timestamp, "ip": ip, "phone": phone,
            "disbursed_account_id": disbursed_account_id, "disbursed_at": disbursed_at,
        })
        self.label(application_id, fraud, story)

    def policy(self, customer_id, start_date, sum_assured, *, product="Term life", policy_id=None):
        if policy_id is None:
            self.policy_no += 1
            policy_id = f"POL-{self.policy_no}"
        self.s.policies.append({
            "policy_id": policy_id, "customer_id": customer_id, "product": product,
            "sum_assured": sum_assured, "start_date": start_date, "status": "active",
        })
        return policy_id

    def claim(self, policy_id, customer_id, amount, timestamp, story, fraud, *, device=None, ip=None,
              phone=None, claim_id=None):
        if claim_id is None:
            self.claim_no += 1
            claim_id = f"CLM-{self.claim_no}"
        self.s.claims.append({
            "claim_id": claim_id, "policy_id": policy_id, "customer_id": customer_id, "amount": amount,
            "status": "submitted", "timestamp": timestamp, "device_id": device, "ip": ip, "phone": phone,
        })
        self.label(claim_id, fraud, story)

    def event(self, account_id, kind, at, details, target=None):
        self.s.account_events.append({
            "event_id": f"EVT-{len(self.s.account_events) + 1}", "account_id": account_id,
            "type": kind, "at": at, "details": details, "target_id": target,
        })

    def label(self, subject_id, is_fraud, story):
        self.s.ground_truth.append({"subject_id": subject_id, "is_fraud": is_fraud, "story": story})


def population(b: Builder) -> list[dict[str, Any]]:
    r = b.r
    accounts = []
    for i in range(200):
        customer = f"CUS-{3000 + i}"
        name = f"{r.choice(FIRST)} {r.choice(LAST)}"
        city = r.choice(CITIES)
        for n in range(2 if i < 40 else 1):
            portfolio = "portfolio-1" if (i + n) % 2 == 0 else "portfolio-2"
            row = b.account(f"ACC-{30000 + len(accounts)}", customer, name, city, portfolio)
            row["device"] = f"DEV-{3000 + i}"
            row["payees"] = [
                (f"BEN-{10000 + r.randint(0, 3999)}", r.choice(PAYEES).replace("_", " "))
                for _ in range(6)
            ]
            row["typical"] = r.uniform(600, 9000)
            accounts.append(row)
    return accounts


def normal_activity(b: Builder, accounts) -> None:
    r = b.r
    for a in accounts:
        for _ in range(24):
            beneficiary, name = r.choice(a["payees"])
            b.pay(a, beneficiary, name, a["typical"] * r.uniform(0.5, 1.5),
                  b.daytime(r.uniform(1, 60)), a["device"], description="Regular payment")
        for _ in range(14):
            b.sign_in(a, a["device"], b.daytime(r.uniform(1, 60)))
        if r.random() < 0.2:
            b.sign_in(a, a["device"], b.daytime(r.uniform(1, 60)), "failure")


def benign_stories(b: Builder, accounts) -> None:
    r = b.r
    picks = r.sample(accounts[40:], 48)
    for a in picks[:14]:  # a new phone, then a large payment
        days = r.uniform(1, 6)
        device = f"DEV-{a['account_id'][-4:]}N"
        when = b.at(days)
        b.sign_in(a, device, when)
        b.event(a["account_id"], "device_enrolled", when, f"{device} passed OTP to registered SIM, usual city {a['city']}", device)
        b.pay(a, a["payees"][0][0], a["payees"][0][1], a["typical"] * 7, b.at(days, -60), device,
              description="Annual fee", story="new_phone_large_payment")
    for a in picks[14:26]:  # paying a new landlord
        days = r.uniform(1, 6)
        beneficiary = f"BEN-{5000 + r.randint(0, 900)}"
        b.event(a["account_id"], "beneficiary_added", b.at(days + 2), f"{beneficiary} added", beneficiary)
        b.pay(a, beneficiary, "New landlord", a["typical"] * 8, b.daytime(days), a["device"],
              description="Rent deposit", story="new_landlord")
    for a in picks[26:38]:  # a one-off large purchase
        b.pay(a, a["payees"][1][0], a["payees"][1][1], a["typical"] * r.uniform(6, 9),
              b.daytime(r.uniform(1, 6)), a["device"], description="Appliance purchase",
              story="one_off_purchase")
    for a in picks[38:]:  # festival gifting bursts
        days = r.uniform(1, 6)
        for i in range(4):
            b.pay(a, f"BEN-{6000 + r.randint(0, 900)}", "Family member", r.uniform(1000, 3000),
                  b.at(days, i * 2), a["device"], description="Festival gift", story="festival_gifting")
    for i in range(6):  # family sharing one phone
        surname = r.choice(LAST)
        city = r.choice(CITIES)
        address = f"{r.randint(1, 400)} Family Lane, {city}"
        device = f"DEV-FAM{i}"
        for j, first in enumerate(r.sample(FIRST, 3)):
            a = b.account(f"ACC-{40000 + i * 10 + j}", f"CUS-{7000 + i * 10 + j}", f"{first} {surname}",
                          city, "portfolio-1" if i % 2 == 0 else "portfolio-2", address=address)
            a["device"] = device
            for _ in range(4):
                b.pay(a, f"BEN-{10000 + r.randint(0, 3999)}", "Grocer", r.uniform(500, 2000),
                      b.daytime(r.uniform(1, 25)), device, description="Household")
            b.sign_in(a, device, b.daytime(r.uniform(1, 25)))
        b.label(device, False, "family_shared_device")


def fraud_stories(b: Builder, accounts) -> None:
    r = b.r
    picks = r.sample(accounts[:40] + accounts[100:], 60)
    for n, a in enumerate(picks[:18]):  # takeover
        days = r.uniform(0.2, 6)
        device = f"DEV-X{n:03d}"
        mule = f"BEN-{8000 + n // 4}"
        for i in range(r.randint(3, 6)):
            b.sign_in(a, device, b.at(days, 50 - i * 3), "failure")
        b.sign_in(a, device, b.at(days, 30))
        b.event(a["account_id"], "password_reset", b.at(days, 25), "Reset by SMS")
        b.pay(a, mule, "Quick Traders", a["typical"] * r.uniform(8, 20), b.at(days, 10), device,
              country=r.choice(["RO", "NG", "VN"]), description="Transfer", story="account_takeover", fraud=True)
    for n in range(4):  # mule fan-out
        mule = f"BEN-{8100 + n}"
        for a in r.sample(picks[18:], 7):
            b.pay(a, mule, "Global Services", a["typical"] * r.uniform(2, 3), b.daytime(r.uniform(1, 6)),
                  a["device"], description="Invoice", story="mule_fan_out", fraud=True)
    for a in picks[18:28]:  # slow bleed, which the rules are meant to miss
        payee = a["payees"][2]
        for _ in range(6):
            b.pay(a, payee[0], payee[1], a["typical"] * r.uniform(0.3, 0.7), b.daytime(r.uniform(1, 25)),
                  a["device"], description="Regular payment", story="slow_bleed", fraud=True)
    for n in range(4):  # unrelated customers on one device
        device = f"DEV-RING{n}"
        for a in r.sample(picks[28:], 4):
            b.sign_in(a, device, b.daytime(r.uniform(1, 20)))
        b.label(device, True, "shared_device_ring")
    for a in r.sample(picks[28:], 6):  # credential stuffing
        days = r.uniform(1, 6)
        device = f"DEV-CS{a['account_id'][-3:]}"
        for i in range(5):
            b.sign_in(a, device, b.at(days, 20 - i), "failure")
        b.sign_in(a, device, b.at(days, 10))
        b.label(a["account_id"], True, "credential_stuffing")


def loans(b: Builder, accounts) -> None:
    r = b.r
    for a in r.sample(accounts, 132):
        b.apply(a["customer_id"], a["device"], r.choice([50000, 100000, 200000, 500000]),
                b.daytime(r.uniform(1, 60)), "normal_application", False)
    for n in range(5):  # one device, several applicants
        device = f"DEV-LOAN{n}"
        base = r.uniform(1, 4) if n < 3 else r.uniform(10, 40)
        for a in r.sample(accounts, 3):
            b.apply(a["customer_id"], device, 300000, b.daytime(base + r.uniform(0, 3)),
                    "multi_applicant_ring", True)


def scenarios(b: Builder) -> None:
    takeover = b.account("ACC-10042", "CUS-10420", "Mira Kulkarni", "Pune", "portfolio-1", years=3)
    takeover["device"] = "DEV-1042"
    for i in range(30):
        b.pay(takeover, "BEN-1200", "Grocer", b.r.uniform(3400, 5000), b.daytime(2 + i * 1.9), "DEV-1042",
              description="Groceries")
    b.sign_in(takeover, "DEV-1042", b.daytime(3))
    for i in range(4):
        b.sign_in(takeover, "DEV-9001", b.at(0, 118 - i * 2), "failure")
    b.sign_in(takeover, "DEV-9001", b.at(0, 108))
    b.event("ACC-10042", "sim_swap", b.at(0, 112), "SIM replaced")
    b.event("ACC-10042", "password_reset", b.at(0, 110), "Reset by SMS")
    b.event("ACC-10042", "device_enrolled", b.at(0, 106), "DEV-9001, foreign IP RO", "DEV-9001")
    for i, (account_id, portfolio) in enumerate(
        [("ACC-10311", "portfolio-1"), ("ACC-10388", "portfolio-1"), ("ACC-10455", "portfolio-1"),
         ("ACC-60001", "portfolio-2"), ("ACC-60002", "portfolio-2"), ("ACC-60003", "portfolio-2")]
    ):
        payer = b.account(account_id, f"CUS-{61000 + i}", f"{FIRST[i]} {LAST[i]}", "Mumbai", portfolio)
        payer["device"] = f"DEV-61{i}"
        b.pay(payer, "BEN-7001", "R K Traders", 90000 + i * 5000, b.daytime(1 + i * 0.7), payer["device"],
              description="Invoice", story="mule_fan_out", fraud=True)
    b.pay(takeover, "BEN-7001", "R K Traders", 185000.0, b.at(0, 90), "DEV-9001", country="RO",
          description="Payment", story="account_takeover", fraud=True, txn_id="TXN-50001")

    benign = b.account("ACC-20017", "CUS-20170", "Tara Bhat", "Pune", "portfolio-1", years=5)
    benign["device"] = "DEV-2017"
    for i in range(30):
        b.pay(benign, "BEN-1300", "Old landlord", b.r.uniform(7500, 10500), b.daytime(2 + i * 1.9), "DEV-2017",
              description="Rent")
    b.sign_in(benign, "DEV-2017", b.daytime(3))
    b.sign_in(benign, "DEV-9002", b.at(0, 180))
    b.event("ACC-20017", "device_enrolled", b.at(0, 180), "DEV-9002 passed OTP to registered SIM, usual city Pune", "DEV-9002")
    b.event("ACC-20017", "beneficiary_added", b.at(2), "BEN-7002 added", "BEN-7002")
    b.pay(benign, "BEN-7002", "S Mehta", 62000.0, b.at(0, 60), "DEV-9002",
          description="Rent deposit, new flat", story="new_landlord", txn_id="TXN-50002")


def insurance(b: Builder, accounts) -> None:
    """Runs after every older story, so their seeded data stays exactly as it was."""
    r = b.r
    picks = r.sample(accounts, 120)
    for a in picks[:90]:  # ordinary policies, some with ordinary claims
        policy = b.policy(a["customer_id"], b.at(r.uniform(120, 900)), r.choice([300000, 500000, 1000000]))
        if r.random() < 0.3:
            b.claim(policy, a["customer_id"], r.choice([20000, 45000, 80000]), b.daytime(r.uniform(1, 45)),
                    "normal_claim", False, device=a["device"])
    for a in picks[90:96]:  # a genuine claim soon after buying cover, the look-alike
        policy = b.policy(a["customer_id"], b.at(r.uniform(12, 25)), 500000)
        b.claim(policy, a["customer_id"], 60000, b.daytime(r.uniform(1, 6)), "early_genuine_claim", False,
                device=a["device"])
    family = [c for c in b.s.customers if c["account_id"].startswith("ACC-4000")]
    for a in family[:2]:  # one household claiming from one phone
        policy = b.policy(a["customer_id"], b.at(300), 300000)
        b.claim(policy, a["customer_id"], 25000, b.daytime(r.uniform(1, 6)), "family_claim", False,
                device=a["device"])
    for n in range(2):  # unrelated customers claiming from one device
        device = f"DEV-CLAIM{n}"
        for a in picks[96 + n * 3:99 + n * 3]:
            policy = b.policy(a["customer_id"], b.at(r.uniform(10, 25)), 800000)
            b.claim(policy, a["customer_id"], 350000, b.daytime(r.uniform(1, 6)), "staged_claim_ring", True,
                    device=device)


RING_DEVICE = "DEV-9003"
RING_IP = "203.0.113.77"


def linked_scenario(b: Builder) -> None:
    """One fraud across lending, core banking and insurance, joined by real identifiers."""
    applicant = b.account("ACC-10077", "CUS-10770", "Neel Rathi", "Nagpur", "portfolio-1", years=4)
    applicant["device"] = "DEV-1077"
    for i in range(30):
        b.pay(applicant, "BEN-1400", "Grocer", b.r.uniform(4000, 7000), b.daytime(2 + i * 1.9), "DEV-1077",
              description="Groceries")
    b.sign_in(applicant, "DEV-1077", b.daytime(3))
    ring = [
        b.account("ACC-10078", "CUS-10780", "Ira Sood", "Nagpur", "portfolio-1", years=2),
        b.account("ACC-10079", "CUS-10790", "Om Kapoor", "Indore", "portfolio-1", years=2),
        b.account("ACC-60010", "CUS-60100", "Ria Dutta", "Bhopal", "portfolio-2", years=2),
    ]
    for n, a in enumerate(ring):
        a["device"] = f"DEV-108{n}"
        for i in range(6):
            b.pay(a, "BEN-1500", "Grocer", b.r.uniform(1500, 3000), b.daytime(2 + i * 4), a["device"],
                  description="Groceries")
        b.sign_in(a, RING_DEVICE, b.at(3, 30 + n * 20), ip=RING_IP)
        b.apply(a["customer_id"], RING_DEVICE, 400000, b.at(3, 20 + n * 20), "multi_applicant_ring", True,
                application_id=f"APP-900{n + 2}", ip=RING_IP, phone=applicant["phone"])
    b.sign_in(applicant, RING_DEVICE, b.at(1, 200), ip=RING_IP)
    b.apply(applicant["customer_id"], RING_DEVICE, 600000, b.at(3), "multi_applicant_ring", True,
            application_id="APP-9001", status="disbursed", ip=RING_IP, phone=applicant["phone"],
            disbursed_account_id="ACC-10077", disbursed_at=b.at(0, 600))
    b.event("ACC-10077", "bank_account_changed", b.at(1), "Disbursement account changed to ACC-10077 on the mobile app", "ACC-10077")
    b.pay(applicant, "BEN-7003", "Zenith Exim", 575000.0, b.at(0, 420), RING_DEVICE,
          description="Payment", story="loan_proceeds_diversion", fraud=True, txn_id="TXN-50003")

    policy = b.policy("CUS-10780", b.at(20), 800000, policy_id="POL-9001")
    b.claim(policy, "CUS-10780", 400000.0, b.at(2), "staged_claim_ring", True, device=RING_DEVICE,
            ip=RING_IP, phone=applicant["phone"], claim_id="CLM-9001")


PARAPHRASED = [
    "Customer entered the one-time code sent to their registered number",
    "Enrolment confirmed with the code texted to the phone on file",
    "One time passcode verified against the registered mobile",
    "Device approved after the customer keyed in the SMS code",
    "Code delivered to the registered SIM was entered correctly",
    "Customer completed two-step check using their registered phone",
    "OTP challenge cleared on the first attempt",
    "Security code from the registered number matched",
    "Authenticated by a verification code on the customer's own SIM",
    "Passcode sent by text was confirmed by the customer",
    "Registered mobile received the code and the customer entered it",
    "Second factor passed using the SIM on record",
]
NEGATED = [
    "OTP failed three times, enrolled by fallback",
    "OTP not completed, enrolment went through the call centre",
    "Customer did not pass OTP",
    "Code sent to the registered SIM was never entered",
    "One-time code expired before it was used",
    "OTP step skipped by support override",
    "Passcode entered incorrectly, device added anyway",
    "No OTP sent, registered number unreachable",
    "SMS code rejected, enrolment forced by agent",
    "Verification code not received by the customer",
    "OTP attempt timed out",
    "Two-step check bypassed",
]


def wording_stories(b: Builder) -> None:
    """New phones whose enrolment text varies, so reading it takes more than a phrase match."""
    r = b.r
    for n, (details, fraud) in enumerate([*((d, False) for d in PARAPHRASED), *((d, True) for d in NEGATED)]):
        a = b.account(f"ACC-{70000 + n}", f"CUS-{70000 + n}", f"{FIRST[n % 20]} {LAST[n % 16]}",
                      r.choice(CITIES), "portfolio-1" if n % 2 == 0 else "portfolio-2")
        a["device"] = f"DEV-7{n:03d}"
        payee = (f"BEN-{14100 + n}", "Grocer")
        for i in range(8):
            b.pay(a, *payee, r.uniform(1500, 3000), b.daytime(8 + i * 3), a["device"], description="Groceries")
        b.sign_in(a, a["device"], b.daytime(9))
        days = r.uniform(1, 5)
        device = f"DEV-7{n:03d}N"
        when = b.at(days)
        b.sign_in(a, device, when)
        b.event(a["account_id"], "device_enrolled", when, details, device)
        b.pay(a, *payee, r.uniform(30000, 60000), b.at(days, -60), device, description="Payment",
              story="failed_otp_enrolment" if fraud else "paraphrased_otp", fraud=fraud)


def generate(now: datetime | None = None) -> Sample:
    b = Builder((now or datetime.now(IST)).astimezone(IST))
    accounts = population(b)
    normal_activity(b, accounts)
    benign_stories(b, accounts)
    fraud_stories(b, accounts)
    loans(b, accounts)
    scenarios(b)
    insurance(b, accounts)
    linked_scenario(b)
    wording_stories(b)
    return b.s
