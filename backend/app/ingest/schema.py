"""Fixed upload columns. These also generate the downloadable templates."""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["id", "text", "amount", "timestamp", "enum"]
DEFAULT_PORTFOLIO = "portfolio-1"


@dataclass(frozen=True)
class Column:
    name: str
    kind: Kind = "text"
    required: bool = True
    choices: tuple[str, ...] = ()
    links_to: str | None = None  # key in known_ids that must already hold this value


@dataclass(frozen=True)
class Dataset:
    name: str
    primary_key: str
    columns: tuple[Column, ...]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


DATASETS = {
    "customers": Dataset(
        "customers",
        "account_id",
        (
            Column("account_id", "id"),
            Column("customer_id", "id"),
            Column("name"),
            Column("phone"),
            Column("email"),
            Column("address"),
            Column("onboarded_at", "timestamp"),
            Column("portfolio", "enum", required=False, choices=("portfolio-1", "portfolio-2")),
        ),
    ),
    "transactions": Dataset(
        "transactions",
        "transaction_id",
        (
            Column("transaction_id", "id"),
            Column("account_id", "id", links_to="own_account_id"),
            Column("beneficiary_id", "id"),
            Column("beneficiary_name"),
            Column("amount", "amount"),
            Column("timestamp", "timestamp"),
            Column("channel", "enum", choices=("mobile", "web", "branch", "atm", "api")),
            Column("status", "enum", choices=("completed", "pending", "failed", "reversed")),
            Column("device_id", "id", required=False),
            Column("ip_country", required=False),
            Column("description", required=False),
        ),
    ),
    "logins": Dataset(
        "logins",
        "login_id",
        (
            Column("login_id", "id"),
            Column("account_id", "id", links_to="own_account_id"),
            Column("customer_id", "id", links_to="own_customer_id"),
            Column("device_id", "id"),
            Column("ip"),
            Column("timestamp", "timestamp"),
            Column("outcome", "enum", choices=("success", "failure")),
        ),
    ),
    "loan_applications": Dataset(
        "loan_applications",
        "application_id",
        (
            Column("application_id", "id"),
            Column("customer_id", "id", links_to="own_customer_id"),
            Column("device_id", "id"),
            Column("amount", "amount"),
            Column("status", "enum", choices=("submitted", "approved", "rejected", "disbursed")),
            Column("timestamp", "timestamp"),
            Column("ip", required=False),
            Column("phone", required=False),
            Column("disbursed_account_id", "id", required=False, links_to="own_account_id"),
            Column("disbursed_at", "timestamp", required=False),
        ),
    ),
    "account_events": Dataset(
        "account_events",
        "event_id",
        (
            Column("event_id", "id"),
            Column("account_id", "id", links_to="own_account_id"),
            Column(
                "type",
                "enum",
                choices=(
                    "password_reset",
                    "sim_swap",
                    "device_enrolled",
                    "beneficiary_added",
                    "bank_account_changed",
                ),
            ),
            Column("at", "timestamp"),
            Column("details", required=False),
            Column("target_id", "id", required=False),
        ),
    ),
    "policies": Dataset(
        "policies",
        "policy_id",
        (
            Column("policy_id", "id"),
            Column("customer_id", "id", links_to="own_customer_id"),
            Column("product"),
            Column("sum_assured", "amount"),
            Column("start_date", "timestamp"),
            Column("status", "enum", choices=("active", "lapsed", "cancelled")),
        ),
    ),
    "claims": Dataset(
        "claims",
        "claim_id",
        (
            Column("claim_id", "id"),
            Column("policy_id", "id", links_to="own_policy_id"),
            Column("customer_id", "id", links_to="own_customer_id"),
            Column("amount", "amount"),
            Column("status", "enum", choices=("submitted", "approved", "rejected", "paid")),
            Column("timestamp", "timestamp"),
            Column("device_id", "id", required=False),
            Column("ip", required=False),
            Column("phone", required=False),
        ),
    ),
}
