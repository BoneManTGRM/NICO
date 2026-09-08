"""Technical classification cannot remove the pre-approval human boundary."""
from nico.comprehensive_native_providers_v5 import _aggregate_record, _normalized_record


def test_material_scanner_hit_still_requires_human_review():
    candidate = _normalized_record(
        commit_sha="a" * 40, scanner="bandit", category="static",
        finding={"test_id": "B602", "filename": "src/synthetic.py", "line_number": 5,
                 "issue_severity": "HIGH", "issue_confidence": "HIGH",
                 "issue_text": "Synthetic shell-invocation finding for technical workflow test."},
    )
    assert candidate["disposition"] == "verified_material"
    assert candidate["human_review_required"] is True
    assert not candidate.get("human_disposition")
    assert not candidate.get("reviewer_identity")
    assert not candidate.get("client_delivery_allowed")


def test_count_only_material_evidence_still_requires_human_review():
    candidate = _aggregate_record(
        commit_sha="a" * 40, scanner="bandit", category="static",
        disposition="verified_material", occurrence_count=2,
    )
    assert candidate["human_review_required"] is True
    assert candidate["evidence_quality"] == "count_only"
    assert candidate["occurrence_count"] == 2
    assert not candidate.get("human_disposition")
