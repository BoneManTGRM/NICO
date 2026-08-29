from __future__ import annotations

import base64
import hashlib
import io
import re
from copy import deepcopy

from pypdf import PdfReader

from nico.comprehensive_api_controller import _final_report_package_integrity_bound
from nico.phase9_comprehensive_report_integration_v1 import (
    _already_finalized_exact_artifact_result,
    finalize_report_package,
)


GENERATED_AT = "2026-08-04T16:15:00Z"
_GENERATED_LABEL = re.compile(
    r"\bGenerated(?:\s+at)?\s*:?[\s<>&a-zA-Z0-9;/=\"'-]{0,80}?"
    r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)",
    re.IGNORECASE,
)


def _result():
    duplicate = {
        "finding_id": "ARCH-1",
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "priority": "P1",
        "status": "open",
        "recommendation": "Split orchestration from presentation logic.",
        "acceptance_criteria": [
            "Operations route complexity is reduced [method: static analysis]",
            "Operations route complexity is reduced [target commit: abc123]",
        ],
    }
    return {
        "report_package": {
            "json": {
                "identity": {
                    "repository": "BoneManTGRM/NICO",
                    "commit_sha": "abc123",
                    "run_id": "run-1",
                    "customer_id": "customer-phase9",
                    "project_id": "project-phase9",
                    "evidence_ledger_id": "ledger-phase9",
                    "generated_at": GENERATED_AT,
                },
                "generated_at": GENERATED_AT,
                "findings_register": [duplicate, dict(duplicate)],
                "executive_findings": [
                    {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
                ],
                "roadmap": [
                    {
                        "work_packages": [
                            {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
                        ]
                    }
                ],
                "backlog": [
                    {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
                ],
                "assessment": {"executive_summary": "Production assessment completed."},
            },
            "generated_at": GENERATED_AT,
            "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "spanish_pdf_filename": "nico-report-es-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "pdf_base64": base64.b64encode(b"%PDF-1.4 proof").decode("ascii"),
        }
    }


def _normalized(value: str) -> str:
    return " ".join(str(value or "").split())


def test_finalizer_canonicalizes_every_surface_filename_and_review_truth():
    output = finalize_report_package(_result())
    package = output["report_package"]
    canonical = package["json"]
    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert finding["title"] == "Reduce complexity in page.tsx"
    assert len(finding["acceptance_criteria"]) == 1
    assert canonical["executive_findings"][0]["title"] == finding["title"]
    assert canonical["roadmap"][0]["work_packages"][0]["title"] == finding["title"]
    assert canonical["backlog"][0]["title"] == finding["title"]
    assert canonical["identity"]["generated_at"] == GENERATED_AT
    assert package["pdf_filename"] == "nico-report-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    assert package["spanish_pdf_filename"] == "nico-report-es-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    assert package["report_finality"] == "automated_draft"
    assert package["approval_status"] == "pending_human_approval"
    assert package["delivery_status"] == "blocked_pending_human_approval"
    assert package["client_delivery_allowed"] is False
    assert package["phase9_release_gate"]["valid"] is True
    assert package["phase9_release_gate"]["production_path_integrated"] is True
    assert package["canonical_truth_sha256"]
    assert package["findings_csv_base64"]


def test_finalizer_renders_one_canonical_summary_timestamp_and_stage_truth():
    package = finalize_report_package(_result())["report_package"]
    canonical = package["json"]
    assessment = canonical["assessment"]
    limited = assessment["limited_review_section_count"]
    markdown = _normalized(package["markdown"])
    rendered_html = _normalized(re.sub(r"<[^>]+>", " ", package["html"]))
    pdf = base64.b64decode(package["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    pdf_text = _normalized("\n".join(page_texts))

    for surface in (markdown, rendered_html, pdf_text):
        assert "BoneManTGRM/NICO" in surface
        assert "abc123" in surface
        assert f"{limited} client-review section(s)" in surface
        assert GENERATED_AT in surface
        assert "completed an authorized Comprehensive Technical Assessment" not in surface
        assert "Six-Month Roadmap · COMPLETE" not in surface
        assert "Stage ID: six_month_roadmap · Status: COMPLETE" not in surface
        assert "Decision-Grade Technical Assessment" not in surface

    markdown_generated = _GENERATED_LABEL.findall(markdown)
    html_generated = _GENERATED_LABEL.findall(rendered_html)
    pdf_generated = _GENERATED_LABEL.findall(pdf_text)
    assert markdown_generated and set(markdown_generated) == {GENERATED_AT}
    assert html_generated and set(html_generated) == {GENERATED_AT}
    assert set(pdf_generated).issubset({GENERATED_AT})

    roadmap = next(
        stage for stage in canonical["stage_summaries"] if stage["stage_id"] == "six_month_roadmap"
    )
    briefing = next(
        stage
        for stage in canonical["stage_summaries"]
        if stage["stage_id"] == "risk_reduction_and_executive_briefing"
    )
    assert roadmap["status"] == "framework_only"
    assert briefing["status"] == "review_required"
    assert all(re.search(r"[A-Za-z0-9]", item) for item in roadmap.get("evidence") or [])

    assert len(reader.pages) <= 45
    assert "Table of Contents" in page_texts[1]
    assert not re.search(r"(?m)^Page\s+\d+\s+\d+$", page_texts[1])
    assert not any(text.strip() == "Comprehensive Technical Assessment" for text in page_texts)


def test_finalizer_is_idempotent():
    first = finalize_report_package(_result())
    second = finalize_report_package(first)
    assert first["report_package"]["json"] == second["report_package"]["json"]
    assert first["report_package"]["pdf_filename"] == second["report_package"]["pdf_filename"]
    assert first["report_package"]["canonical_truth_sha256"] == second["report_package"]["canonical_truth_sha256"]
    assert second["report_package"]["pdf_filename"].count(
        "AUTOMATED-DRAFT-PENDING-APPROVAL"
    ) == 1


def test_stale_exact_artifact_alias_cannot_bypass_v2_rebuild():
    stale = deepcopy(finalize_report_package(_result()))
    package = stale["report_package"]
    legacy_bytes = b"legacy,v2,findings,csv\n"
    package["findings_csv_base64"] = base64.b64encode(legacy_bytes).decode(
        "ascii"
    )
    package["findings_csv_sha256"] = hashlib.sha256(legacy_bytes).hexdigest()

    assert _final_report_package_integrity_bound(package) is False
    assert _already_finalized_exact_artifact_result(stale) is False

    rebuilt = finalize_report_package(stale)["report_package"]

    assert _final_report_package_integrity_bound(rebuilt) is True
    assert base64.b64decode(
        rebuilt["findings_csv_base64"], validate=True
    ) == rebuilt["findings_csv"].encode("utf-8")
