from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import nico.cli as legacy
from nico.local_scoring_repair_service import apply_rye, repairs_for, rye_score


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCAN_SERVICE = ROOT / "nico" / "local_scan_service.py"
SCORING_SERVICE = ROOT / "nico" / "local_scoring_repair_service.py"


def finding(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "finding_exact_1",
        "finding_id": "finding_exact_1",
        "category": "insecure_webhook",
        "severity": "high",
        "confidence": 0.9,
        "title": "Webhook signature missing",
        "affected_file": "webhook.py",
        "business_impact": "Forged events can trigger unauthorized actions.",
        "verification_method": "Reject missing or invalid signatures.",
    }
    payload.update(overrides)
    return payload


def test_rye_score_and_application_match_legacy_contract_exactly() -> None:
    source = finding()
    memory = [
        {"category": "insecure_webhook"},
        {"finding_category": "insecure_webhook"},
        {"category": "dependency_risk"},
    ]
    original_source = deepcopy(source)
    original_memory = deepcopy(memory)

    assert rye_score(source, memory) == legacy.rye_score(source, memory)
    assert apply_rye([source], memory) == legacy.apply_rye([source], memory)
    assert source == original_source
    assert memory == original_memory
    assert "rye" not in source


def test_repair_plans_match_legacy_contract_with_deterministic_identity(monkeypatch) -> None:
    scored = apply_rye([finding()], [{"category": "insecure_webhook"}])
    ids = ["repair_exact_1", "repair_exact_2", "repair_exact_3"]
    legacy_ids = iter(ids)
    extracted_ids = iter(ids)
    created_at = "2026-07-13T23:45:00+00:00"

    monkeypatch.setattr(legacy, "new_id", lambda prefix: next(legacy_ids))
    monkeypatch.setattr(legacy, "now", lambda: created_at)

    expected = legacy.repairs_for(scored, [{"category": "insecure_webhook"}])
    actual = repairs_for(
        scored,
        [{"category": "insecure_webhook"}],
        id_factory=lambda prefix: next(extracted_ids),
        clock=lambda: created_at,
    )

    assert actual == expected
    assert [item["repair_type"] for item in actual] == ["minimal", "moderate", "strong"]
    assert [item["autonomy_level"] for item in actual] == [1, 2, 3]
    assert all(item["approval_requirement"] == "human_review_required_before_any_code_change" for item in actual)
    assert all(item["status"] == "suggested" for item in actual)
    assert all(item["candidate_status"] == "report_only_unverified_candidate" for item in actual)
    assert all(item["mode"] == "report_only" for item in actual)
    assert all("Do not edit, commit, push, deploy, or open a pull request" in item["codex_ready_patch_prompt"] for item in actual)
    assert all(item["code_change_applied"] is False for item in actual)
    assert all(item["automatic_application_allowed"] is False for item in actual)
    assert all(item["automatic_commit_allowed"] is False for item in actual)
    assert all(item["automatic_pull_request_allowed"] is False for item in actual)
    assert all(item["code_suggestion"]["status"] == "available" for item in actual)
    assert all(item["code_suggestion"]["mode"] == "report_only" for item in actual)
    assert all(item["code_suggestion"]["verified_fix"] is False for item in actual)
    assert all("production_deploy" not in item for item in actual)


def test_unknown_category_preserves_smallest_safe_fallback_and_local_boundary() -> None:
    source = finding(
        category="unknown_category",
        severity="low",
        title="Unclassified defensive finding",
        affected_file="",
        verification_method="",
    )
    plans = repairs_for(
        [source],
        id_factory=lambda prefix: f"{prefix}_fixed",
        clock=lambda: "2026-07-13T23:45:00+00:00",
    )

    assert len(plans) == 3
    assert all(item["smallest_safe_change"] == "Apply smallest defensive fix and verify." for item in plans)
    assert all(item["affected_files"] == [] for item in plans)
    assert all(item["approval_requirement"] == "human_review_required_before_any_code_change" for item in plans)
    assert all(item["rollback_plan"].startswith("Revert only the approved targeted change") for item in plans)
    assert all(item["code_suggestion"]["status"] == "unavailable" for item in plans)
    assert all(item["automatic_application_allowed"] is False for item in plans)


def test_repair_planning_does_not_mutate_findings_or_memory() -> None:
    findings = apply_rye([finding()], [])
    memory = [{"category": "insecure_webhook", "note": "retained"}]
    original_findings = deepcopy(findings)
    original_memory = deepcopy(memory)

    repairs_for(
        findings,
        memory,
        id_factory=lambda prefix: f"{prefix}_fixed",
        clock=lambda: "2026-07-13T23:45:00+00:00",
    )

    assert findings == original_findings
    assert memory == original_memory


def test_canonical_scan_service_sources_scoring_and_repairs_from_extracted_service() -> None:
    scan_source = LOCAL_SCAN_SERVICE.read_text(encoding="utf-8")
    scoring_source = SCORING_SERVICE.read_text(encoding="utf-8")

    assert "from nico.local_scoring_repair_service import apply_rye, repairs_for" in scan_source
    assert "from nico.cli" not in scan_source
    assert "from nico.cli" not in scoring_source
    assert "Any code change, production change" in scoring_source
    assert "automatic_application_allowed" in scoring_source
    assert "report_only_unverified_candidate" in scoring_source
