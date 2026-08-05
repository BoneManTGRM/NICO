from __future__ import annotations

import io
import re
from copy import deepcopy
from pathlib import Path

import pytest
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from nico.comprehensive_full_report_finish_v1 import (
    _WORKSHEET_TITLES,
    assert_dark_table_contrast,
    assert_full_data_parity,
    canonical_generation_timestamp,
    classify_report_proof,
    digest_markup,
    enforce_dark_table_contrast,
    filename_markup,
    humanize_structured_value,
    install_reportlab_dark_header_contrast,
    sanitize_stage_structures,
)


def _pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph(line, styles["BodyText"]) for line in lines]
    SimpleDocTemplate(buffer, invariant=1).build(story)
    return buffer.getvalue()


def _full_canonical() -> dict:
    finding = {
        "finding_id": "NICO-FINDING-EXACT-1",
        "path": "nico/example.py",
        "line": 42,
        "disposition": "human_review_required",
    }
    stages = [{"title": title} for title in _WORKSHEET_TITLES]
    stages.extend({"title": f"Additional section {index}"} for index in range(5))
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "run_id": "comprun_real_evidence",
            "commit_sha": "a" * 40,
            "generated_at": "2026-08-05T00:00:00Z",
            "customer_id": "Acme Holdings",
            "project_id": "NICO review",
        },
        "assessment": {
            "sections": [{"id": "code_audit", "score": 96}],
            "requested_scanner_records": 1,
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 89,
        },
        "stage_summaries": stages,
        "scanner_execution_records": [{"scanner_name": "bandit", "completed": True}],
        "canonical_scanner_finding_register": {"findings": []},
        "client_finding_remediation_register": {"code_findings": [finding]},
        "artifact_manifest": {"artifacts": []},
        "approval": {
            "decision": "pending",
            "client_delivery_allowed": False,
        },
        "report_finality": "automated_draft",
        "approval_status": "pending_human_approval",
        "delivery_status": "client_delivery_blocked",
        "client_delivery_allowed": False,
    }


def test_dark_blue_header_paragraphs_are_forced_to_white() -> None:
    gray = ParagraphStyle(
        "GrayHeader",
        parent=getSampleStyleSheet()["BodyText"],
        textColor=colors.HexColor("#475569"),
    )
    header = Paragraph("Metric", gray)
    table = Table([[header, Paragraph("Value", gray)], ["one", "two"]])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#475569")),
            ]
        )
    )

    enforce_dark_table_contrast(table)
    assert_dark_table_contrast(table)

    assert table._cellStyles[0][0].color == colors.white
    assert all(fragment.textColor == colors.white for fragment in header.frags)
    assert gray.textColor == colors.HexColor("#475569")


def test_shared_reportlab_style_patch_covers_future_tables() -> None:
    install_reportlab_dark_header_contrast()
    gray = ParagraphStyle(
        "GrayHeaderAfterInstall",
        parent=getSampleStyleSheet()["BodyText"],
        textColor=colors.HexColor("#475569"),
    )
    table = Table([[Paragraph("Header", gray)]])
    table.setStyle(
        TableStyle(
            [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e"))]
        )
    )

    assert_dark_table_contrast(table)


@pytest.mark.parametrize(
    "filename",
    [
        "nico-comprun_example-findings.csv",
        "nico-comprun_example-candidate-register.json",
        "nico-comprun_example-report.html",
        "nico-comprun_example-summary.md",
    ],
)
def test_filename_extensions_are_not_orphaned(filename: str) -> None:
    markup = filename_markup(filename, maximum=28)
    lines = markup.split("<br/>")
    extension = Path(filename).suffix

    assert all(len(line) > 1 for line in lines)
    assert lines[-1].endswith(extension)
    assert extension in lines[-1]


def test_digest_is_balanced_and_reconstructs_to_exactly_64_hex_characters() -> None:
    digest = "0123456789abcdef" * 4
    markup = digest_markup(digest)
    lines = markup.split("<br/>")

    assert [len(line) for line in lines] == [32, 32]
    assert markup.replace("<br/>", "") == digest
    assert re.fullmatch(r"[0-9a-f]{64}", markup.replace("<br/>", ""))


def test_generation_timestamp_is_projected_from_canonical_metadata() -> None:
    canonical = {
        "identity": {},
        "report_metadata": {"report_generated_at": "2026-08-05T01:02:03Z"},
    }

    assert canonical_generation_timestamp(canonical) == "2026-08-05T01:02:03Z"


def test_raw_workflow_mapping_becomes_readable_labels() -> None:
    raw = (
        "workflow_outcome_classes: {'failure': 10, 'success': 81, 'cancelled': 2, "
        "'skipped': 3, 'timed_out': 1, 'unknown': 9, 'in_progress': 4}"
    )

    rendered = humanize_structured_value(raw)

    assert rendered == (
        "Workflow Outcome Classes: Failed: 10; Successful: 81; Cancelled: 2; "
        "Skipped: 3; Timed out: 1; Unknown: 9; In progress: 4"
    )
    assert "{" not in rendered
    assert "'failure'" not in rendered


def test_stage_cleanup_removes_raw_mapping_without_changing_other_evidence() -> None:
    stage = {
        "title": "Historical Trends and Change Failure",
        "evidence": [
            {"success": 81, "failure": 10, "unknown": 9},
            "Retained evidence line.",
        ],
    }

    cleaned = sanitize_stage_structures(stage)

    assert cleaned["evidence"] == [
        "Successful: 81; Failed: 10; Unknown: 9",
        "Retained evidence line.",
    ]
    assert stage["evidence"][0] == {"success": 81, "failure": 10, "unknown": 9}


def test_sparse_fixture_cannot_satisfy_full_data_parity() -> None:
    sparse = {
        "identity": {"run_id": "phase9-proof-123"},
        "assessment": {"sections": [{"id": "code_audit"}]},
        "stage_summaries": [{"title": "Six-Month Roadmap"}],
    }

    assert classify_report_proof(sparse) == "sparse_fixture"
    with pytest.raises(ValueError, match="sparse fixture"):
        assert_full_data_parity(sparse, "", "", _pdf(["fixture"]))


def test_full_data_parity_requires_all_eight_worksheets_and_exact_findings() -> None:
    canonical = _full_canonical()
    lines = [
        *_WORKSHEET_TITLES,
        "Review-Required Candidate Register",
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "Human Review and Acceptance Gate",
        "Complete Exact-Source Index",
        "NICO-FINDING-EXACT-1",
        "Generated 2026-08-05T00:00:00Z",
    ]

    result = assert_full_data_parity(
        canonical,
        "\n".join(lines),
        "<p>" + "</p><p>".join(lines) + "</p>",
        _pdf(lines),
    )

    assert result["proof_kind"] == "full_comprehensive"
    assert result["worksheet_count"] == 8
    assert result["exact_source_finding_count"] == 1


def test_presentation_cleanup_does_not_change_scores_or_dispositions() -> None:
    canonical = _full_canonical()
    before = deepcopy(canonical)

    sanitize_stage_structures(
        {
            "evidence": [{"success": 81, "failure": 10}],
            "findings": ["NICO-FINDING-EXACT-1"],
        }
    )
    filename_markup("nico-comprun_real_evidence-findings.csv")
    digest_markup("a" * 64)

    assert canonical["assessment"]["technical_score"] == before["assessment"]["technical_score"]
    assert (
        canonical["assessment"]["canonical_evidence_adjusted_score"]
        == before["assessment"]["canonical_evidence_adjusted_score"]
    )
    assert (
        canonical["client_finding_remediation_register"]
        == before["client_finding_remediation_register"]
    )
    assert canonical["approval"] == before["approval"]


def test_automated_draft_and_delivery_blocked_lifecycle_is_unchanged() -> None:
    canonical = _full_canonical()

    assert canonical["report_finality"] == "automated_draft"
    assert canonical["approval_status"] == "pending_human_approval"
    assert canonical["delivery_status"] == "client_delivery_blocked"
    assert canonical["client_delivery_allowed"] is False
