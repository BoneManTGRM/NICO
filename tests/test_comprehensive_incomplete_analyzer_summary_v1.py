from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

from nico import client_report_completion_v2 as completion
from nico import comprehensive_client_ready_projection_v1 as projection
from nico.comprehensive_client_report_render_v60 import (
    validate_existing_report_accuracy,
)
from nico.comprehensive_incomplete_analyzer_summary_v1 import (
    canonical_incomplete_analyzer_count,
    install_comprehensive_incomplete_analyzer_summary,
)

ROOT = Path(__file__).resolve().parents[1]


def _register() -> dict:
    return {
        "code_findings": [],
        "operational_findings": [],
        "summary": {
            "finding_population_reconciled": True,
            "decision_finding_count": 0,
            "exact_source_code_finding_count": 0,
            "operational_or_context_finding_count": 0,
        },
    }


def _canonical(incomplete: int = 0) -> dict:
    records = [
        {
            "scanner_name": f"scanner-{index}",
            "completed": index >= incomplete,
            "status": "completed" if index >= incomplete else "failed",
            "applicable": True,
        }
        for index in range(9)
    ]
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_incomplete_analyzer_summary",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 90,
        },
        "scanner_execution_records": records,
        "incomplete_applicable_analyzers": incomplete,
        "client_readiness_contract": {
            "analyzer_execution_coverage": 100 if incomplete == 0 else 78,
            "coverage_denominator": 9,
            "maturity_label": "Exceptional",
        },
        "review_candidate_summary": {
            "review_required_total": 614,
            "verified_material_total": 0,
        },
    }


def _extracted(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_installer_binds_projection_and_completion_aliases() -> None:
    state = install_comprehensive_incomplete_analyzer_summary()

    assert state["markdown_bound"] is True
    assert state["pdf_bound"] is True
    assert state["completion_markdown_alias_bound"] is True
    assert state["completion_pdf_alias_bound"] is True
    assert completion.compact_client_markdown is projection.compact_client_markdown
    assert (
        completion.render_evidence_review_gate_pdf
        is projection.render_evidence_review_gate_pdf
    )


def test_zero_incomplete_count_is_retained_in_markdown_html_and_pdf() -> None:
    install_comprehensive_incomplete_analyzer_summary()
    canonical = _canonical(0)
    markdown = completion.compact_client_markdown(
        "# NICO\n\n## Delivery Status\nBlocked.\n",
        canonical,
        _register(),
        spanish=False,
    )
    pdf = completion.render_evidence_review_gate_pdf(
        canonical,
        _register(),
        spanish=False,
    )

    assert markdown.count("Incomplete applicable analyzers: 0") == 1
    assert "Incomplete applicable analyzers: 0" in _extracted(pdf)
    assert canonical_incomplete_analyzer_count(canonical) == 0


def test_spanish_summary_is_localized_once_without_english_presentation_copy() -> None:
    install_comprehensive_incomplete_analyzer_summary()
    canonical = _canonical(0)
    markdown = completion.compact_client_markdown(
        "# NICO\n\n## Estado de entrega\nBloqueada.\n",
        canonical,
        _register(),
        spanish=True,
    )
    pdf = completion.render_evidence_review_gate_pdf(
        canonical,
        _register(),
        spanish=True,
    )
    extracted = _extracted(pdf)

    assert markdown.count("Analizadores aplicables incompletos: 0") == 1
    assert "Incomplete applicable analyzers: 0" not in markdown
    assert extracted.count("Analizadores aplicables incompletos: 0") == 1
    assert "Incomplete applicable analyzers: 0" not in extracted


def test_nonzero_incomplete_count_is_not_silently_rewritten_to_zero() -> None:
    install_comprehensive_incomplete_analyzer_summary()
    canonical = _canonical(2)
    markdown = completion.compact_client_markdown(
        "# NICO\n\n## Delivery Status\nBlocked.\n",
        canonical,
        _register(),
        spanish=False,
    )
    pdf = completion.render_evidence_review_gate_pdf(
        canonical,
        _register(),
        spanish=False,
    )

    assert canonical_incomplete_analyzer_count(canonical) == 2
    assert "Incomplete applicable analyzers: 2" in markdown
    assert "Incomplete applicable analyzers: 2" in _extracted(pdf)
    assert "Incomplete applicable analyzers: 0" not in markdown


def test_existing_accuracy_gate_accepts_compact_report_with_explicit_count() -> None:
    install_comprehensive_incomplete_analyzer_summary()
    canonical = _canonical(0)
    generated = completion.compact_client_markdown(
        "\n".join(
            (
                "# NICO COMPREHENSIVE",
                "Canonical Technical Scorecard",
                "Analyzer execution coverage is 100%",
                "Maturity Exceptional",
                "Evidence Appendix",
                "Human Review and Acceptance Gate",
                "## Delivery Status",
                "Blocked.",
            )
        ),
        canonical,
        _register(),
        spanish=False,
    )
    pdf = completion.render_evidence_review_gate_pdf(
        canonical,
        _register(),
        spanish=False,
    )
    package = {
        "json": canonical,
        "markdown": generated,
        "html": f"<main>{generated}</main>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
    }

    result = validate_existing_report_accuracy(package)

    assert result["canonical_incomplete_analyzer_count"] == 0
    assert result["false_incomplete_analyzers_absent"] is True
    assert result["production_pdf_validated"] is True


def test_phase17_installs_summary_before_client_composition() -> None:
    source = (
        ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
    ).read_text(encoding="utf-8")

    assert "install_comprehensive_incomplete_analyzer_summary" in source
    assert "_INCOMPLETE_ANALYZER_SUMMARY" in source
    assert '"canonical_incomplete_analyzer_summary_retained": True' in source
