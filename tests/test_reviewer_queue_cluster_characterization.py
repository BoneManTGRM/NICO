"""Full output fingerprints captured from main before cluster validation extraction."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_reviewer_queue_producer_consumer_routing import _consume, _payload

# Each case starts with the real producer's complete grouped/individual fixture.
CHANGES = {
    "cluster_identity": ("cluster", "cluster_id", ""),
    "members_missing": ("cluster", "candidate_ids", None),
    "members_malformed": ("cluster", "candidate_ids", [None, {}, "human-a"]),
    "members_duplicate": ("cluster", "candidate_ids", ["human-a", "human-a"]),
    "members_unknown": ("cluster", "candidate_ids", ["human-a", "unknown"]),
    "declared_count": ("cluster", "candidate_record_count", 0),
    "declared_size": ("cluster", "cluster_size", 0),
    "cluster_routes": ("cluster", "review_routing_classes", []),
    "reason": ("cluster", "cluster_reason", ""),
    "basis": ("cluster", "homogeneous_evidence_basis", ""),
    "representative": ("cluster", "representative_candidate_id", "unknown"),
    "human_routing": ("cluster", "grouped_human_review_cluster", False),
    "group_evidence": ("cluster", "homogeneous_evidence", False),
    "group_verdict": ("cluster", "homogeneous_verdict", False),
    "disposition_required": ("cluster", "underlying_candidate_disposition_required", None),
    "group_eligibility": ("cluster", "grouped_review_eligible", False),
    "commit": ("candidate", "exact_commit_sha", "b" * 40),
    "human_disposition": ("candidate", "human_disposition", "accepted"),
    "delivery": ("candidate", "client_delivery_allowed", True),
    "human_required": ("candidate", "human_review_required", False),
    "candidate_cluster": ("candidate", "cluster_id", "other"),
    "candidate_size": ("candidate", "cluster_size", 0),
    "membership": ("candidate", "cluster_candidate_ids", []),
    "candidate_representative": ("candidate", "representative_candidate_id", "unknown"),
    "candidate_eligibility": ("candidate", "grouped_review_eligible", False),
    "candidate_evidence": ("candidate", "homogeneous_evidence", False),
    "candidate_verdict": ("candidate", "homogeneous_verdict", False),
    "candidate_unit": ("candidate", "review_unit_id", "other"),
    "candidate_attention": ("candidate", "review_requires_individual_attention", True),
    "mixed_attention": ("candidate", "review_routing_class", "QUALITY_CONTROL_ELIGIBLE"),
}
CASES = ["valid", *CHANGES, "duplicate_cluster", "malformed_cluster", "single_group_member",
         "individual_grouped", "individual_attention", "multiple_independent_failures", "reordered_members"]


def fixture(case):
    payload = deepcopy(_payload())
    register = payload["candidate_register"]
    clusters = register["review_workload_clusters"]
    cluster = next(item for item in clusters if item["grouped_human_review_cluster"])
    candidate = next(item for item in register["findings"] if item["candidate_id"] == "human-a")
    if case in CHANGES:
        target, field, value = CHANGES[case]
        (cluster if target == "cluster" else candidate)[field] = deepcopy(value)
    elif case == "duplicate_cluster":
        clusters.append(deepcopy(cluster))
    elif case == "malformed_cluster":
        clusters.append(None)
    elif case == "single_group_member":
        cluster["candidate_ids"] = ["human-a"]
    elif case in {"individual_grouped", "individual_attention"}:
        individual = next(item for item in register["findings"] if item["candidate_id"] == "individual")
        individual["grouped_review_eligible" if case == "individual_grouped" else "review_requires_individual_attention"] = case == "individual_grouped"
    elif case == "multiple_independent_failures":
        cluster.update(cluster_reason="", homogeneous_evidence_basis="", representative_candidate_id="unknown", underlying_candidate_disposition_required=False)
        candidate.update(exact_commit_sha="wrong", client_delivery_allowed=True, homogeneous_evidence=False)
    elif case == "reordered_members":
        cluster["candidate_ids"].reverse()
    return payload


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.mark.parametrize("locale", ["en", "es-MX"])
@pytest.mark.parametrize("case", CASES)
def test_complete_model_and_error_order_match_main(case, locale):
    expected = json.loads(Path(__file__).with_suffix(".json").read_text())
    model = _consume(fixture(case), locale)
    assert fingerprint(model) == expected[locale][case]
    assert bool(model["integrityErrors"]) == (case != "valid")
