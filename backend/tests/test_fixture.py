import json
from pathlib import Path

from contracts import CaseDetail, Investigation, Step
from demo.make_fixture import OUT, build


def test_committed_fixture_matches_the_contract():
    fixture = json.loads(Path(OUT).read_text())
    assert fixture == build()
    CaseDetail.model_validate(fixture["case"])
    investigation = Investigation.model_validate(fixture["investigation"])
    steps = [Step.model_validate(s) for s in fixture["steps"]]

    ids = {e.id for e in investigation.evidence}
    cited = {i for f in investigation.report.findings for i in f.evidence_ids}
    assert cited <= ids
    assert {i for s in steps for i in s.evidence_ids} == ids
