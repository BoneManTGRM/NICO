from copy import deepcopy

import unittest

from nico.report_scanner_outcomes import outcomes, summary
from nico.report_score_explanation import LABELS_ES, score_explanation


def report():
    identity = dict(repository="sample/project", commit_sha="a"*40, run_id="run-1")
    rows = [dict(scanner_name=name, execution_status="completed", execution_observed=True,
                 execution_evidence_verified=True, retained_ci_evidence_verified=False)
            for name in "eslint gitleaks npm-audit osv-scanner pip-audit semgrep trufflehog bandit typescript".split()]
    rows[-2].update(execution_status="failed", finding_count=0)
    rows[-1].update(execution_observed=False, execution_evidence_verified=False,
                    retained_ci_evidence_verified=True)
    evidence = dict(identity, verification_status="verified", scanner_records=rows)
    contract = dict(scoring_model_version="technical-minus-named-assurance-deductions.v1",
                    technical_score=95, evidence_adjusted_score=91, candidate_volume_penalty=0,
                    incomplete_analyzer_penalty=4, missing_raw_payload_penalty=0,
                    other_assurance_penalties={}, assurance_penalty=4, score_formula="95 - 0 - 0 - 4 - 0 = 91")
    return identity, dict(identity, score_contract=contract, nico_release_provenance=dict(
        assessment_run_id="run-1", assessed_repository_commit="a"*40, scanner_execution_evidence=evidence))


def check_mixed_origins_failure_and_retained_math(es):
    identity, assessment = report()
    original = deepcopy(assessment)
    result = summary(outcomes(assessment, identity), es)
    assert ("completados en esta ejecución: 7" if es else "completed in this run: 7") in result
    assert "1 (typescript)" in result and "1 (bandit)" in result
    assert ("no demuestra la ausencia" if es else "does not establish the absence") in result
    lines = score_explanation(assessment, lambda s: LABELS_ES.get(s, s) if es else s)
    assert any(line.endswith(": bandit") for line in lines)
    assert any(line.endswith("95 - 0 - 0 - 4 - 0 = 91") for line in lines)
    assert assessment == original


def check_no_success_or_named_deduction_from_unbound_records(case):
    identity, assessment = report()
    provenance = assessment["nico_release_provenance"]
    evidence = provenance["scanner_execution_evidence"]
    if case == "unverified": evidence["verification_status"] = "unverified"
    if case == "duplicate": evidence["scanner_records"].append(evidence["scanner_records"][0])
    if case == "wrong_run": evidence["run_id"] = "older"
    if case == "wrong_sha": assessment["commit_sha"] = "b"*40
    if case == "selected": evidence["selected_scanner"] = "bandit"
    if case == "missing": provenance.clear()
    assert outcomes(assessment, identity) is None
    assert "See individual scanner records" in summary(None, False)
    assert not any("bandit" in s for s in score_explanation(assessment))


def check_unknown_and_timeout_not_completed_and_no_inferred_points():
    identity, assessment = report()
    rows = assessment["nico_release_provenance"]["scanner_execution_evidence"]["scanner_records"]
    rows[0].update(execution_status="timed_out")
    rows[1].update(execution_observed=False)
    groups = outcomes(assessment, identity)
    assert len(groups["current"]) == 5
    assert groups["other"] == ["gitleaks"] and groups["timed_out"] == ["eslint"]
    assessment["score_contract"]["score_formula"] = "unsupported"
    assert "unavailable" in score_explanation(assessment)[0]

class TestReportScannerTruth(unittest.TestCase):
    def test_mixed(self):
        for spanish in (False, True):
            with self.subTest(spanish=spanish):
                check_mixed_origins_failure_and_retained_math(spanish)

    def test_unbound(self):
        for case in ("unverified", "duplicate", "wrong_run", "wrong_sha", "selected", "missing"):
            with self.subTest(case=case):
                check_no_success_or_named_deduction_from_unbound_records(case)

    def test_unknown_and_timeout(self):
        check_unknown_and_timeout_not_completed_and_no_inferred_points()
