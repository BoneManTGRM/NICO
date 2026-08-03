from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import client_report_completion_v2 as completion
from nico.comprehensive_placeholder_sanitization_v1 import (
    VERSION,
    assert_parser_placeholders_absent,
    install_comprehensive_placeholder_sanitization,
    sanitize_canonical_placeholder_identifiers,
)


ROOT = Path(__file__).resolve().parents[1]
PHASE17 = ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
SHA = "a" * 40


def _hotspot() -> dict:
    return {
        "name": "<arrow>",
        "path": "apps/web/app/AssessmentMidLiveStatusTransport.tsx",
        "line": 294,
        "end_line": 412,
        "cyclomatic_complexity": 35,
        "cognitive_complexity": 50,
        "loc": 119,
        "grade": "E",
        "method": "typescript_compiler_ast",
    }


def _finding() -> dict:
    return {
        "finding_id": "NICO-FINDING-PLACEHOLDER",
        "id": "NICO-FINDING-PLACEHOLDER",
        "priority": "P1",
        "category": "architecture",
        "status": "review_required",
        "title": "Reduce complexity in anonymous callback",
        "decision_title": "Reduce complexity in <arrow>",
        "symbol": "anonymous callback",
        "path": "apps/web/app/AssessmentMidLiveStatusTransport.tsx",
        "line": 294,
        "end_line": 412,
        "location": "apps/web/app/AssessmentMidLiveStatusTransport.tsx:294",
        "fact": "cyclomatic_complexity=35; method=typescript_compiler_ast",
        "interpretation": "Concentrated branching in `anonymous callback`.",
        "business_impact": "Concentrated branch logic increases regression risk.",
        "recommendation": "Extract bounded typed hooks or services.",
        "acceptance_criteria": [
            "The exact-SHA rerun no longer reports complexity above 30 at the retained source anchor."
        ],
        "exact_commit_match": True,
        "production_scope": True,
    }


def _canonical() -> dict:
    hotspot = _hotspot()
    finding = _finding()
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_placeholder_test",
        },
        "architecture_hotspots": [hotspot],
        "canonical_findings": [finding],
        "findings_register": [finding],
        "decision_grade_findings_register": [finding],
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 90,
            "maturity_signal": {
                "score": 93,
                "presented_score": 93,
                "level": "Exceptional",
            },
            "architecture_hotspots": [hotspot],
            "canonical_findings": [finding],
            "findings_register": [finding],
            "decision_grade_findings_register": [finding],
        },
        "scanner_execution_records": [],
        "repository_evidence": {
            "file_evidence": {
                "sampled_paths": [
                    "apps/web/app/AssessmentMidLiveStatusTransport.tsx"
                ]
            }
        },
    }


def _pdf(*lines: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    y = 740
    for line in lines:
        document.drawString(48, y, line)
        y -= 18
    document.showPage()
    document.save()
    return output.getvalue()


def test_sanitizer_cleans_mirrored_findings_and_hotspots_without_score_drift() -> None:
    source = _canonical()
    result = sanitize_canonical_placeholder_identifiers(source)

    assert result["architecture_hotspots"][0]["name"] == "anonymous callback"
    assert result["assessment"]["architecture_hotspots"][0]["name"] == "anonymous callback"
    assert result["findings_register"][0]["decision_title"] == (
        "Reduce complexity in anonymous callback"
    )
    assert result["assessment"]["decision_grade_findings_register"][0][
        "decision_title"
    ] == "Reduce complexity in anonymous callback"
    assert result["architecture_hotspots"][0]["path"] == (
        "apps/web/app/AssessmentMidLiveStatusTransport.tsx"
    )
    assert result["architecture_hotspots"][0]["line"] == 294
    assert result["architecture_hotspots"][0]["cyclomatic_complexity"] == 35
    assert result["assessment"]["technical_score"] == 93
    assert result["assessment"]["canonical_evidence_adjusted_score"] == 90
    assert "<arrow>" not in json.dumps(result, sort_keys=True).casefold()
    assert result["v2_pipeline_contract"][
        "anonymous_callbacks_retain_exact_source_anchors"
    ] is True


def test_installer_binds_existing_completion_paths_before_composition() -> None:
    state = install_comprehensive_placeholder_sanitization()

    assert state["canonical_sync_bound"] is True
    assert state["scanner_reconciliation_bound"] is True
    assert state["final_surface_gate_bound"] is True
    assert state["scores_unchanged"] is True
    assert state["scanner_dispositions_unchanged"] is True
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False


def test_prepare_client_package_removes_placeholder_from_canonical_truth() -> None:
    install_comprehensive_placeholder_sanitization()
    prepared = completion.prepare_client_report_package({"json": _canonical()})
    canonical = prepared["json"]

    assert "<arrow>" not in json.dumps(canonical, sort_keys=True).casefold()
    assert canonical["assessment"]["technical_score"] == 93
    assert canonical["assessment"]["canonical_evidence_adjusted_score"] == 90
    assert canonical["assessment"]["architecture_hotspots"][0]["line"] == 294
    assert canonical["assessment"]["architecture_hotspots"][0]["name"] == (
        "anonymous callback"
    )


def test_final_surface_gate_rejects_placeholder_in_canonical_json() -> None:
    install_comprehensive_placeholder_sanitization()
    register = {
        "code_findings": [],
        "operational_findings": [],
        "summary": {},
    }

    with pytest.raises(
        ValueError,
        match=r"canonical report JSON retained parser placeholder <arrow>",
    ):
        completion._validate_final_surfaces(
            {"name": "<arrow>"},
            register,
            "AUTOMATED DRAFT",
            "<!doctype html><p>AUTOMATED DRAFT</p>",
            _pdf("AUTOMATED DRAFT"),
        )


def test_final_surface_gate_rejects_placeholder_in_client_markdown() -> None:
    install_comprehensive_placeholder_sanitization()
    register = {
        "code_findings": [],
        "operational_findings": [],
        "summary": {},
    }

    with pytest.raises(
        ValueError,
        match=r"client Markdown retained parser placeholder <arrow>",
    ):
        completion._validate_final_surfaces(
            {},
            register,
            "AUTOMATED DRAFT\nReduce complexity in <arrow>",
            "<!doctype html><p>AUTOMATED DRAFT</p>",
            _pdf("AUTOMATED DRAFT"),
        )


def test_direct_placeholder_assertion_detects_html_escaped_token() -> None:
    with pytest.raises(ValueError, match=r"client HTML retained parser placeholder"):
        assert_parser_placeholders_absent(
            "Reduce complexity in &lt;arrow&gt;",
            surface="client HTML",
        )


def test_phase17_installs_sanitizer_before_final_client_composition() -> None:
    source = PHASE17.read_text(encoding="utf-8")

    assert "install_comprehensive_placeholder_sanitization" in source
    assert "_PLACEHOLDER_SANITIZATION" in source
    assert source.index("_PLACEHOLDER_SANITIZATION =") < source.index(
        "_COMPACT_DESIGN_MARKER_GATE ="
    )
    assert '"parser_placeholders_absent": True' in source
    assert VERSION == "nico.comprehensive-placeholder-sanitization.v1"
