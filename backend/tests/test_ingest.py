import io
import json

import pytest
from openpyxl import Workbook

from ingest import DATASETS, FileRejected, check_file, template_csv

KNOWN = {"account_id": {"ACC-1", "ACC-2"}, "customer_id": {"CUS-1"}, "transaction_id": {"TXN-9"}}
HEADER = "transaction_id,account_id,beneficiary_id,beneficiary_name,amount,timestamp,channel,status"
GOOD = "TXN-1,ACC-1,BEN-1,Asha,500.50,2026-10-30T10:00:00,mobile,completed"


def txns(*rows, header=HEADER):
    return "\n".join([header, *rows]).encode()


def check(content, filename="t.csv", dataset="transactions"):
    return check_file(dataset, filename, content, KNOWN)


def test_valid_row_loads_with_normalised_values():
    rows, result = check(txns(GOOD))
    assert result.loaded == 1 and result.rejected == []
    assert rows[0]["amount"] == 500.5
    assert rows[0]["timestamp"] == "2026-10-30T10:00:00+05:30"
    assert rows[0]["description"] is None


@pytest.mark.parametrize(
    "row, reason",
    [
        ("TXN-1,ACC-1,BEN-1,Asha,,2026-10-30,mobile,completed", "Missing amount."),
        ("TXN-1,ACC-1,BEN-1,Asha,abc,2026-10-30,mobile,completed", "not a number"),
        ("TXN-1,ACC-1,BEN-1,Asha,-5,2026-10-30,mobile,completed", "greater than 0"),
        ("TXN-1,ACC-1,BEN-1,Asha,NaN,2026-10-30,mobile,completed", "greater than 0"),
        ("TXN-1,ACC-404,BEN-1,Asha,5,2026-10-30,mobile,completed", "Unknown account_id"),
        ("TXN-1,ACC-1,BEN-1,Asha,5,30/10/2026,mobile,completed", "not an ISO date"),
        ("TXN-1,ACC-1,BEN-1,Asha,5,2026-10-30,fax,completed", "channel must be one of"),
        ("TXN-9,ACC-1,BEN-1,Asha,5,2026-10-30,mobile,completed", "Duplicate transaction_id"),
        ("TXN-1,ACC-1,BEN-1,Asha,5,2026-10-30,mobile,completed,extra", "more value(s)"),
    ],
)
def test_bad_row_is_reported_and_good_rows_still_load(row, reason):
    rows, result = check(txns(GOOD.replace("TXN-1", "TXN-2"), row))
    assert [r["transaction_id"] for r in rows] == ["TXN-2"]
    assert result.total_rows == 2
    assert result.rejected[0].row == 3
    assert reason in result.rejected[0].reasons[0]


def test_every_problem_in_a_row_is_listed():
    _, result = check(txns("TXN-1,ACC-404,BEN-1,Asha,abc,2026-10-30,fax,completed"))
    assert len(result.rejected[0].reasons) == 3


def test_duplicate_within_a_file():
    rows, result = check(txns(GOOD, GOOD))
    assert len(rows) == 1 and "Duplicate" in result.rejected[0].reasons[0]


def test_rupee_and_comma_amounts():
    rows, _ = check(txns('TXN-1,ACC-1,BEN-1,Asha,"₹1,85,000",2026-10-30,mobile,completed'))
    assert rows[0]["amount"] == 185000.0


def test_missing_required_column_rejects_the_file():
    with pytest.raises(FileRejected, match="amount"):
        check(txns("TXN-1", header="transaction_id"))


def test_extra_columns_and_blank_rows_are_reported():
    rows, result = check(txns(GOOD + ",x", ",,,,,,,,", header=HEADER + ",notes"))
    assert len(rows) == 1
    assert result.ignored_columns == ["notes"]
    assert result.blank_rows == 1 and result.total_rows == 1


def test_headers_are_forgiving_and_bom_is_handled():
    content = b"\xef\xbb\xbf" + txns(GOOD, header=HEADER.replace("transaction_id", " Transaction ID"))
    assert check(content)[1].loaded == 1


def test_excel():
    book = Workbook()
    sheet = book.active
    sheet.append(HEADER.split(","))
    sheet.append(["TXN-1", "ACC-1", "BEN-1", "Asha", 5000.0, "2026-10-30", "mobile", "completed"])
    sheet.append(["TXN-2", "ACC-1", "BEN-1", "Asha", None, "2026-10-30", "mobile", "completed"])
    buffer = io.BytesIO()
    book.save(buffer)
    rows, result = check(buffer.getvalue(), "t.xlsx")
    assert rows[0]["amount"] == 5000.0
    assert result.rejected[0].row == 3


def test_json_list_and_wrapper():
    record = dict(zip(HEADER.split(","), GOOD.split(",")))
    assert check(json.dumps([record]).encode(), "t.json")[1].loaded == 1
    assert check(json.dumps({"rows": [record, 5]}).encode(), "t.json")[1].rejected[0].row == 2


@pytest.mark.parametrize(
    "filename, content",
    [("t.pdf", b"x"), ("t.json", b"{bad"), ("t.json", b"{}"), ("t.xlsx", b"not excel"), ("t.csv", b"")],
)
def test_unreadable_files_are_rejected(filename, content):
    with pytest.raises(FileRejected):
        check(content, filename)


def test_portfolio_defaults_and_is_validated():
    header = "account_id,customer_id,name,phone,email,address,onboarded_at,portfolio"
    good = "ACC-3,CUS-3,A,1,a@x.test,Pune,2024-01-01,"
    bad = "ACC-4,CUS-4,A,1,a@x.test,Pune,2024-01-01,portfolio-9"
    rows, result = check("\n".join([header, good, bad]).encode(), dataset="customers")
    assert rows[0]["portfolio"] == "portfolio-1"
    assert result.rejected[0].row == 3


@pytest.mark.parametrize("name", DATASETS)
def test_templates_list_every_column(name):
    assert template_csv(name).strip().split(",") == DATASETS[name].column_names
