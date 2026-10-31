from agent.verification import verify
from contracts import Evidence, Finding, ReportDraft


def ev(id, data):
    return Evidence(id=id, investigation_id="I", kind="transaction", source_ref=id, data=data, collected_at="t")


EVIDENCE = [
    ev("EV-1", {"transaction_id": "TXN-50001", "amount": 185000.0, "timestamp": "2026-10-31T16:21:00+05:30", "account_id": "ACC-10042"}),
    ev("EV-2", {"median_outgoing_30d": 4200.0, "paying_accounts_7d": 6}),
]


def errors(statement, ids=("EV-1",)):
    draft = ReportDraft(assessment="suspicious", summary="s", limitations=[], recommended_actions=[],
                        findings=[Finding(statement=statement, evidence_ids=list(ids))])
    return verify(draft, EVIDENCE)


def test_matching_facts_pass_in_every_amount_format():
    for amount in ("185000", "₹1,85,000", "185,000.00", "₹ 185000"):
        assert errors(f"TXN-50001 on ACC-10042 sent {amount} on 2026-10-31.") == []


def test_small_counts_are_not_treated_as_amounts():
    assert errors("6 accounts paid in 7 days over a 30-day window.", ["EV-2"]) == []


def test_wrong_amount_fails():
    assert "Amount ₹1,84,000" in errors("Sent ₹1,84,000.")[0]


def test_right_amount_cited_to_wrong_evidence_fails():
    assert errors("Sent 185000.", ["EV-2"])


def test_wrong_date_and_record_id_fail():
    assert len(errors("TXN-99999 on ACC-10099 on 2026-10-01.")) == 3


def test_unknown_or_missing_citations_fail():
    assert "unknown Evidence EV-9" in errors("Fine.", ["EV-9"])[0]
    assert "cites no Evidence" in errors("Fine.", [])[0]


def test_no_findings_fails():
    draft = ReportDraft(assessment="not_suspicious", summary="s", findings=[], limitations=[], recommended_actions=[])
    assert verify(draft, EVIDENCE) == ["The report has no findings."]


def test_record_id_in_the_source_ref_counts():
    row = Evidence(id="EV-3", investigation_id="I", kind="account_event",
                   source_ref="ACC-10042/sim_swap/t", data={"type": "sim_swap"}, collected_at="t")
    draft = ReportDraft(assessment="suspicious", summary="s", limitations=[], recommended_actions=[],
                        findings=[Finding(statement="ACC-10042 had a SIM swap.", evidence_ids=["EV-3"])])
    assert verify(draft, [row]) == []


def test_no_action_is_rejected_on_a_suspicious_report():
    draft = ReportDraft(assessment="suspicious", summary="s", limitations=[],
                        recommended_actions=["hold_transaction", "no_action"],
                        findings=[Finding(statement="Fine.", evidence_ids=["EV-1"])])
    assert "no_action" in verify(draft, EVIDENCE)[0]


def test_a_true_value_in_an_uncited_record_gets_its_citation():
    from agent.verification import complete_citations
    draft = ReportDraft(assessment="suspicious", summary="s", limitations=[], recommended_actions=[],
                        findings=[Finding(statement="Sent ₹1,85,000 on ACC-10042.", evidence_ids=["EV-2"])])
    fixed = complete_citations(draft, EVIDENCE)
    assert fixed.findings[0].evidence_ids == ["EV-2", "EV-1"]
    assert verify(fixed, EVIDENCE) == []


def test_an_invented_value_still_fails_after_completion():
    from agent.verification import complete_citations
    draft = ReportDraft(assessment="suspicious", summary="s", limitations=[], recommended_actions=[],
                        findings=[Finding(statement="Sent ₹7,77,777.", evidence_ids=["EV-1"])])
    assert verify(complete_citations(draft, EVIDENCE), EVIDENCE)


def test_an_invented_value_in_the_summary_fails():
    def draft(summary):
        return ReportDraft(assessment="suspicious", summary=summary, limitations=[], recommended_actions=[],
                           findings=[Finding(statement="Fine.", evidence_ids=["EV-1"])])
    assert verify(draft("ACC-10042 sent ₹1,85,000."), EVIDENCE) == []
    assert "Summary" in verify(draft("ACC-10042 sent ₹9,99,999."), EVIDENCE)[0]


def test_a_partial_record_id_fails():
    assert errors("ACC-1 sent money.")
    assert errors("TXN-5 was large.")


def test_digits_inside_an_id_or_date_do_not_count_as_an_amount():
    assert "Amount 10042" in errors("Sent 10042.")[0]
    assert "₹2026" in errors("Sent ₹2026.")[0]


def test_a_date_inside_a_timestamp_still_matches():
    assert errors("Paid on 2026-10-31.") == []


def test_decimal_and_small_rupee_amounts_are_checked():
    assert errors("Sent ₹50.")
    assert errors("Sent 185000.50.")
