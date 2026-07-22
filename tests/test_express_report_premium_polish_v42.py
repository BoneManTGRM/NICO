from __future__ import annotations

import io

from pypdf import PdfReader

from nico.express_report_premium_polish_v42 import _branded_pdf, _reconcile_report_truth


def _result() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "generated_at": "2026-07-22T17:04:24Z",
        "maturity_signal": {"score": 87, "presented_score": 87},
        "evidence_adjusted_score": 85,
        "executive_summary": "NICO completed a defensive read-only assessment and retained review-limited scanner evidence.",
        "repair_intelligence": {
            "candidates": [
                {"title": "Consolidate runtime compatibility installers"},
                {"title": "Triage dependency candidates"},
                {"title": "Verify deployment identity"},
            ]
        },
        "sections": [
            {
                "id": "dependency_health",
                "evidence": [
                    "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner.",
                    "Exact-snapshot pip-audit status=completed; findings=0.",
                ],
                "findings": ["npm-audit returned 2 finding(s) requiring human triage."],
                "unavailable": ["Full pip-audit, npm audit, and OSV Scanner CLI artifacts are still required before claiming final scanner-clean dependency status."],
            },
            {
                "id": "secrets_review",
                "evidence": ["Exact-snapshot trufflehog status=completed; findings=1."],
                "findings": ["gitleaks ended with status timeout; its output requires human review before client-facing conclusions."],
                "unavailable": [],
            },
            {
                "id": "ci_cd",
                "evidence": [
                    "GitHub Actions workflows found: .github/workflows/a.yml, .github/workflows/b.yml, .github/workflows/c.yml, .github/workflows/d.yml, .github/workflows/e.yml, .github/workflows/f.yml.",
                ],
                "findings": ["Historical workflow reliability includes 11 non-success run(s)."],
                "unavailable": [],
            },
            {
                "id": "architecture_debt",
                "evidence": ["Estimated call graph edges: 21746; max file cyclomatic complexity: 246."],
                "findings": [
                    "Source-file footprint is large and increases review scope; repository size is not scored as technical debt by itself.",
                    "Total source LOC is high for an Express review and increases review depth; size alone does not reduce maintainability score.",
                    "Function-level complexity risk is concentrated in 421 source file(s).",
                ],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "evidence": [
                    "Commit velocity: 100 commits over 180 days.",
                    "Client/human acceptance evidence unavailable: no approved final report was found.",
                ],
                "findings": [],
                "unavailable": ["Stakeholder context is required."],
            },
        ],
    }


def _sample_pdf() -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    c.drawString(72, 720, "OLD COVER")
    c.showPage()
    c.drawString(72, 720, "NICO Express evidence-bound report only human review required")
    c.drawString(72, 700, "Evidence assurance remains review-limited; analyzer failures do not reduce the technical-health percentage.")
    c.drawString(72, 40, "Page 2 of 3")
    c.showPage()
    c.drawString(72, 720, "Executive Decision Brief")
    c.drawString(72, 700, "Retained decision content")
    c.save()
    return buffer.getvalue()


def test_report_truth_reconciles_remaining_client_contradictions() -> None:
    result = _reconcile_report_truth(_result())
    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")
    ci = next(item for item in result["sections"] if item["id"] == "ci_cd")
    architecture = next(item for item in result["sections"] if item["id"] == "architecture_debt")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert not any("Full pip-audit" in item for item in dependency["unavailable"])
    assert any("final scanner-clean dependency claim is withheld" in item for item in dependency["unavailable"])
    assert any("Gitleaks execution timed out" in item for item in secrets["unavailable"])
    assert len(ci["evidence"]) == 1
    assert "6 workflow(s)" in ci["evidence"][0]
    assert not any(item.startswith("Source-file footprint") for item in architecture["findings"])
    assert any(item.startswith("Scale context") for item in architecture["evidence"])
    assert "maximum file cyclomatic complexity 246" in architecture["score_rationale"]
    assert "11 non-success" in ci["score_rationale"]
    assert not any(item.startswith("Client/human acceptance") for item in velocity["evidence"])
    assert any(item.startswith("Client/human acceptance") for item in velocity["unavailable"])


def test_branded_pdf_replaces_old_cover_and_removes_orphan_page() -> None:
    result = _result()
    output = _branded_pdf(_sample_pdf(), result)
    reader = PdfReader(io.BytesIO(output))
    assert len(reader.pages) == 2
    cover_text = reader.pages[0].extract_text() or ""
    assert "NICO EXPRESS" in cover_text
    assert "OLD COVER" not in cover_text
    assert "EVIDENCE-BOUND ENGINEERING INTELLIGENCE" in cover_text
    assert "Executive Decision Brief" in (reader.pages[1].extract_text() or "")
    assert result["express_pdf_premium_cover"]["orphan_pages_removed"] == 1
    assert result["express_pdf_premium_cover"]["navigation_outline_rebuilt"] is True
