from __future__ import annotations

from copy import deepcopy

from nico.canonical_assessment_contract_v1 import (
    HUMAN_EVIDENCE_MODULES,
    VERSION,
    attach_canonical_assessment_contract,
    build_canonical_assessment_contract,
    normalize_depth,
)


def _payload() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "run_id": "assessment_run_contract_v1",
        "customer_id": "customer_contract",
        "project_id": "project_contract",
        "assessment_depth": "strategic",
        "report_language": "en",
        "repository_snapshot": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "scanner": {
            "scan_id": "scanner_contract_v1",
            "status": "complete",
        },
        "assessment": {
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code quality",
                    "presented_score": 86,
                    "score_band_label": "STRONG",
                    "assurance_label": "VERIFIED",
                    "risk_disposition": "GREEN",
                },
                {
                    "id": "secrets_review",
                    "label": "Secrets posture",
                    "presented_score": 86,
                    "score_band_label": "STRONG",
                    "assurance_label": "REVIEW LIMITED",
                    "risk_disposition": "YELLOW",
                },
            ]
        },
        "reports": {
            "pdf_sha256": "c" * 64,
        },
        "evidence_artifact_bundle": {
            "bundle_hash": "d" * 64,
        },
    }


def test_depth_aliases_map_to_one_core_or_strategic_contract() -> None:
    assert normalize_depth("express") == "core"
    assert normalize_depth("core") == "core"
    assert normalize_depth("comprehensive") == "strategic"
    assert normalize_depth("full") == "strategic"
    assert normalize_depth("strategic") == "strategic"


def test_contract_binds_one_identity_and_is_deterministic() -> None:
    payload = _payload()
    first = build_canonical_assessment_contract(payload)
    reordered = {key: payload[key] for key in reversed(list(payload))}
    second = build_canonical_assessment_contract(reordered)

    assert first["schema_version"] == VERSION
    assert first["status"] == "complete"
    assert first["identity"]["repository"] == "BoneManTGRM/NICO"
    assert first["identity"]["commit_sha"] == "a" * 40
    assert first["identity"]["tree_sha"] == "b" * 40
    assert first["identity"]["run_id"] == "assessment_run_contract_v1"
    assert first["identity"]["scanner_run_id"] == "scanner_contract_v1"
    assert first["identity"]["assessment_depth"] == "strategic"
    assert first["contract_sha256"] == second["contract_sha256"]


def test_score_assurance_and_risk_remain_separate() -> None:
    contract = build_canonical_assessment_contract(_payload())
    secrets = next(
        item
        for item in contract["canonical_score_and_assurance_ledger"]
        if item["control_id"] == "secrets_review"
    )

    assert secrets["technical_score"] == 86
    assert secrets["technical_band"] == "STRONG"
    assert secrets["evidence_assurance"] == "REVIEW LIMITED"
    assert secrets["risk_disposition"] == "YELLOW"
    assert contract["technical_score_assurance_and_risk_are_separate"] is True


def test_core_and_strategic_share_schema_without_fabricating_human_evidence() -> None:
    payload = _payload()
    core = build_canonical_assessment_contract(payload, depth="core")
    strategic = build_canonical_assessment_contract(payload, depth="strategic")

    assert core["schema_version"] == strategic["schema_version"]
    assert core["independent_core_and_strategic_scorecards_allowed"] is False
    assert strategic["independent_core_and_strategic_scorecards_allowed"] is False

    core_status = {item["module_id"]: item for item in core["module_status"]}
    strategic_status = {item["module_id"]: item for item in strategic["module_status"]}
    for module_id in HUMAN_EVIDENCE_MODULES:
        assert core_status[module_id]["status"] == "not_in_core_scope"
        assert strategic_status[module_id]["status"] == "not_assessed"
        assert strategic_status[module_id]["repository_inference_prohibited"] is True

    assert strategic["human_evidence_may_be_inferred_from_repository"] is False


def test_missing_identity_is_review_limited_and_never_delivery_authorized() -> None:
    contract = build_canonical_assessment_contract({"assessment_depth": "strategic"})

    assert contract["status"] == "review_limited"
    assert contract["missing_required_identity"] == ["repository", "commit_sha", "run_id"]
    assert contract["automatic_approval"] is False
    assert contract["human_review_required"] is True
    assert contract["client_delivery_allowed"] is False


def test_attachment_does_not_mutate_the_source_payload() -> None:
    payload = _payload()
    original = deepcopy(payload)
    attached = attach_canonical_assessment_contract(payload)

    assert payload == original
    assert "canonical_assessment_contract" not in payload
    assert attached["canonical_assessment_contract"]["status"] == "complete"
