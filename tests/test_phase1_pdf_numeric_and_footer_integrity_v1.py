from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from nico.candidate_phase1_report_workload_pdf_v1 import render_phase1_evidence_review_gate_pdf
from nico.comprehensive_incomplete_analyzer_summary_v1 import _overlay_pdf_summary
from nico.comprehensive_platform_parity_summary_v1 import overlay_platform_parity_summary


def _canonical() -> dict:
    """Synthetic NICO-only report with populated tables and known numeric zeros."""
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_" + "b" * 32,
        },
        "authorized": True,
        "assessment": {"technical_score": 80, "evidence_adjusted_score": 75},
        "scanner_execution_records": [
            {"completed": True, "scanner_name": f"fixture-scanner-{i}"}
            for i in range(9)
        ],
        "review_candidate_summary": {
            "review_required_total": 18,
            "verified_material_total": 0,
            "by_category": {
                "dependency": {"raw": 5, "material": 0, "review_required": 5},
                "secret": {"raw": 4, "material": 0, "review_required": 4},
                "static": {"raw": 9, "material": 0, "review_required": 9},
            },
        },
        "technical_triage": {
            "status": "complete",
            "fresh_technical_triage_completed": 10,
            "workload_metrics": {
                "total_candidates": 18,
                "technical_triage_completed": 18,
                "technical_triage_coverage_pct": 100.0,
                "stable_carry_forward_count": 8,
                "candidates_requiring_individual_human_attention": 4,
                "grouped_human_review_candidate_count": 6,
                "grouped_review_cluster_count": 2,
                "human_review_work_units": 6,
                "quality_control_sample_pool": 8,
                "automated_not_actionable_candidate_count": 8,
                "human_attention_candidate_count_before_grouping": 10,
                "end_to_end_review_workload_reduction_count": 12,
                "end_to_end_review_workload_reduction_pct": 66.67,
            },
        },
    }


def _render(spanish: bool) -> bytes:
    return render_phase1_evidence_review_gate_pdf(
        _canonical(),
        {"code_findings": [
            {"finding_id": f"NICO-SYNTHETIC-{i}", "path": "nico/fixture.py", "line": i}
            for i in (1, 2, 3)
        ]},
        spanish=spanish,
    )


@pytest.mark.parametrize("spanish", [False, True])
def test_evidence_pdf_displays_zero_counts_instead_of_blank_cells(spanish: bool) -> None:
    # A truthiness conversion used to erase numeric zero in these table cells.
    text = " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(_render(spanish))).pages
    )
    text = " ".join(text.split())
    operational = (
        "Unidades de revisión operativa o contextual"
        if spanish else "Operational/context review work units"
    )
    assert f"{operational} 0" in text
    categories = ("Dependencias", "Secretos", "Análisis estático") if spanish else (
        "Dependency", "Secret", "Static"
    )
    for category, count in zip(categories, (5, 4, 9), strict=True):
        assert f"{category} {count} 0 {count}" in text
    # Missing intake data must remain missing, not be changed into a numeric zero.
    assert ("No proporcionado" if spanish else "Not supplied") in text


@pytest.mark.parametrize("spanish", [False, True])
def test_evidence_pdf_body_clears_later_summary_footer_overlays(spanish: bool) -> None:
    # The downstream platform overlay paints y=38..56 white. Report body text
    # previously entered that band and the last evidence line was partly erased.
    source = _render(spanish)
    body_runs: list[tuple[str, float]] = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            baseline = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            body_runs.append((text.strip(), baseline - size * 0.25))

    reader = PdfReader(io.BytesIO(source))
    for page in reader.pages:
        page.extract_text(visitor_text=visit)
    assert body_runs
    overlaps = [(text, bottom) for text, bottom in body_runs if bottom < 56]
    assert not overlaps, overlaps

    composed = _overlay_pdf_summary(source, _canonical(), spanish=spanish)
    composed = overlay_platform_parity_summary(composed, _canonical(), spanish=spanish)
    output = PdfReader(io.BytesIO(composed))
    assert len(output.pages) == len(reader.pages)
    text = " ".join(" ".join(p.extract_text().split()) for p in output.pages)
    assert (
        "Hallazgos con fuente exacta en el índice: 3" if spanish
        else "Exact-source findings in index: 3"
    ) in text
    assert ("Analizadores aplicables incompletos: 0" if spanish else "Incomplete applicable analyzers: 0") in text
    assert ("paridad de plataforma en ejecución no evaluada" if spanish else "runtime platform parity not assessed") in text


@pytest.mark.parametrize("spanish", [False, True])
def test_footer_clearance_does_not_orphan_the_final_evidence_line(spanish: bool) -> None:
    # Reserving the footer must not leave a count alone on an otherwise empty page.
    pages = PdfReader(io.BytesIO(_render(spanish))).pages
    label = "Hallazgos con fuente exacta en el índice" if spanish else "Exact-source findings in index"
    heading = "Límite del paquete del cliente" if spanish else "Client package boundary"
    evidence_page = next(page.extract_text() for page in pages if label in page.extract_text())
    assert heading in evidence_page
