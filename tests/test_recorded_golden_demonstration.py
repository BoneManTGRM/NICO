from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.build_golden_demonstration import (
    GoldenDemonstrationFailure,
    build_golden_demonstration,
    render_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "golden" / "manifest.json"
WORKFLOW = ROOT / ".github" / "workflows" / "recorded-golden-demonstration.yml"


def test_builder_records_all_representative_fixtures_and_boundaries() -> None:
    artifact = build_golden_demonstration(MANIFEST)

    assert artifact["artifact_schema"] == "nico.golden_demonstration.v1"
    assert artifact["status"] == "passed"
    assert artifact["demonstration_kind"] == "recorded_synthetic_golden_suite"
    assert artifact["synthetic"] is True
    assert artifact["live_claim"] is False
    assert artifact["fixture_count"] == 3
    assert {item["id"] for item in artifact["fixtures"]} == {
        "unavailable_evidence",
        "complete_review_boundary",
        "mixed_risk_repair_boundary",
    }
    assert artifact["boundaries"] == {
        "all_synthetic": True,
        "all_review_required": True,
        "none_approved": True,
        "none_client_ready": True,
        "all_delivery_blocked": True,
        "no_certification_claim": True,
    }
    assert all(len(item["source_sha256"]) == 64 for item in artifact["fixtures"])
    assert "not a live assessment" in artifact["guardrail"]


def test_builder_is_deterministic_for_identical_sources() -> None:
    first = build_golden_demonstration(MANIFEST)
    second = build_golden_demonstration(MANIFEST)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert render_markdown(first) == render_markdown(second)
    assert "generated_at" not in first
    assert "timestamp" not in json.dumps(first).lower()


def test_markdown_is_bounded_and_keeps_synthetic_guardrail_visible() -> None:
    artifact = build_golden_demonstration(MANIFEST)
    markdown = render_markdown(artifact)

    assert markdown.startswith("# NICO Recorded Synthetic Golden Demonstration")
    assert "Live claim: **false**" in markdown
    assert "synthetic_unavailable_assessment" in markdown
    assert "synthetic_complete_review_required_assessment" in markdown
    assert "synthetic_mixed_risk_repair_assessment" in markdown
    assert artifact["guardrail"] in markdown
    assert len(markdown) < 20_000


def _copy_suite(tmp_path: Path) -> Path:
    source_dir = MANIFEST.parent
    target_dir = tmp_path / "golden"
    target_dir.mkdir(parents=True)
    for path in source_dir.glob("*.json"):
        (target_dir / path.name).write_bytes(path.read_bytes())
    return target_dir / "manifest.json"


def test_builder_fails_closed_when_fixture_claims_live_status(tmp_path: Path) -> None:
    manifest_path = _copy_suite(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture_path = manifest_path.parent / manifest["fixtures"][0]["path"]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["live_claim"] = True
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(GoldenDemonstrationFailure, match="not explicitly synthetic and non-live"):
        build_golden_demonstration(manifest_path)


def test_builder_fails_closed_when_review_or_delivery_boundary_is_weakened(tmp_path: Path) -> None:
    manifest_path = _copy_suite(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture_path = manifest_path.parent / manifest["fixtures"][1]["path"]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["review"]["client_ready"] = True
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(GoldenDemonstrationFailure, match="weakened the human-review or client-readiness boundary"):
        build_golden_demonstration(manifest_path)

    manifest_path = _copy_suite(tmp_path / "second")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture_path = manifest_path.parent / manifest["fixtures"][2]["path"]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["delivery"]["status"] = "ready"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(GoldenDemonstrationFailure, match="did not keep synthetic delivery blocked"):
        build_golden_demonstration(manifest_path)


def test_builder_fails_closed_on_unsafe_paths_and_coverage_drift(tmp_path: Path) -> None:
    manifest_path = _copy_suite(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unsafe = deepcopy(manifest)
    unsafe["fixtures"][0]["path"] = "../escape.json"
    manifest_path.write_text(json.dumps(unsafe), encoding="utf-8")

    with pytest.raises(GoldenDemonstrationFailure, match="local JSON filenames"):
        build_golden_demonstration(manifest_path)

    manifest_path = _copy_suite(tmp_path / "coverage")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage_requirements"].append("undeclared_required_case")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(GoldenDemonstrationFailure, match="Golden coverage mismatch"):
        build_golden_demonstration(manifest_path)


def test_workflow_builds_twice_compares_and_uploads_recorded_artifacts() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in source
    assert "push:" in source
    assert "workflow_dispatch:" in source
    assert source.count("scripts/build_golden_demonstration.py") == 2
    assert "cmp first/golden-demonstration.json second/golden-demonstration.json" in source
    assert "cmp first/golden-demonstration.md second/golden-demonstration.md" in source
    assert "actions/upload-artifact@v4" in source
    assert "audit-results/golden-demonstration.json" in source
    assert "audit-results/golden-demonstration.md" in source
    assert "permissions:\n  contents: read" in source
