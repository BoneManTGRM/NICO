from __future__ import annotations

import base64

from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package


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
                "identity": {"repository": "BoneManTGRM/NICO", "commit_sha": "abc123", "run_id": "run-1"},
                "findings_register": [duplicate, dict(duplicate)],
                "executive_findings": [{"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}],
                "roadmap": [{"work_packages": [{"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}]}],
                "backlog": [{"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}],
                "assessment": {"executive_summary": "Production assessment completed."},
            },
            "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "spanish_pdf_filename": "nico-report-es-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "pdf_base64": base64.b64encode(b"%PDF-1.4 proof").decode("ascii"),
        }
    }


def test_finalizer_canonicalizes_every_surface_and_filename():
    output = finalize_report_package(_result())
    package = output["report_package"]
    canonical = package["json"]
    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert finding["title"].startswith("operations page")
    assert len(finding["acceptance_criteria"]) == 1
    assert canonical["executive_findings"][0]["title"] == finding["title"]
    assert canonical["roadmap"][0]["work_packages"][0]["title"] == finding["title"]
    assert canonical["backlog"][0]["title"] == finding["title"]
    assert package["pdf_filename"] == "nico-report-FINAL-PENDING-APPROVAL.pdf"
    assert package["spanish_pdf_filename"] == "nico-report-es-FINAL-PENDING-APPROVAL.pdf"
    assert package["phase9_release_gate"]["valid"] is True
    assert package["phase9_release_gate"]["production_path_integrated"] is True
    assert package["canonical_truth_sha256"]
    assert package["findings_csv_base64"]


def test_finalizer_is_idempotent():
    first = finalize_report_package(_result())
    second = finalize_report_package(first)
    assert first["report_package"]["json"] == second["report_package"]["json"]
    assert first["report_package"]["pdf_filename"] == second["report_package"]["pdf_filename"]
    assert first["report_package"]["canonical_truth_sha256"] == second["report_package"]["canonical_truth_sha256"]
