from __future__ import annotations

from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence


def test_explicit_false_security_evidence_is_preserved() -> None:
    register = {
        "findings": [
            {
                "candidate_id": "FALSE-EVIDENCE",
                "finding_id": "FALSE-EVIDENCE",
                "category": "static",
                "scanner": "semgrep",
                "rule_id": "rule.false",
                "source_path": "nico/example.py",
                "line": 10,
                "occurrence_count": 1,
            }
        ]
    }
    scan = {
        "scanner_results": [
            {
                "scanner_name": "semgrep",
                "category": "static",
                "findings": [
                    {
                        "check_id": "rule.false",
                        "path": "nico/example.py",
                        "line": 10,
                        "direct_dependency": False,
                        "installed_version_affected": False,
                        "current_resolution_fixed": False,
                        "first_party_reachable": False,
                        "environment_relevant": False,
                        "exploitable": False,
                        "supported_security_boundary_crossed": False,
                        "verified": False,
                        "synthetic": False,
                        "executable_code": False,
                        "comment_or_string": False,
                        "mitigated": False,
                        "secret": "must-not-retain",
                    }
                ],
            }
        ]
    }

    result = enrich_canonical_candidate_evidence(register, scan)
    evidence = result["findings"][0]["deterministic_evidence"]

    for field in (
        "direct_dependency",
        "installed_version_affected",
        "current_resolution_fixed",
        "first_party_reachable",
        "environment_relevant",
        "exploitable",
        "supported_security_boundary_crossed",
        "verified",
        "synthetic",
        "executable_code",
        "comment_or_string",
        "mitigated",
    ):
        assert field in evidence
        assert evidence[field] is False

    assert "secret" not in evidence
    assert result["candidate_evidence_context"]["candidate_counts_changed"] is False
    assert result["candidate_evidence_context"]["canonical_dispositions_changed"] is False
