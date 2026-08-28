from __future__ import annotations

import io

from pypdf import PdfReader

from nico import comprehensive_manifest_navigation_v1 as nav
from nico import comprehensive_spanish_presentation_parity_v1 as parity_v1
from nico import comprehensive_spanish_presentation_parity_v2 as parity_v2
from nico.comprehensive_spanish_presentation_parity_v2 import (
    _localized_register,
    _render_manifest_spanish,
    _safe_es,
    _toc_page_spanish,
)
from nico.v2_dark_branded_cover import _cover


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def _normalized_pdf_text(pdf: bytes) -> str:
    return " ".join(_pdf_text(pdf).split())


def test_boundary_safe_spanish_translation_does_not_corrupt_source_tokens() -> None:
    translated = _safe_es(
        "Workflow counts are below the threshold while ScannerWorkflowPage remains at "
        "apps/web/app/scanner-workflow/page.tsx."
    )
    assert "workfbaja" not in translated
    assert "bebaja" not in translated
    assert "ScannerWorkflowPage" in translated
    assert "apps/web/app/scanner-workflow/page.tsx" in translated


def test_spanish_phrase_patterns_are_compiled_once_per_authored_source() -> None:
    for module in (parity_v1, parity_v2):
        module._safe_replace_pattern.cache_clear()
        first = module._safe_replace_pattern("Workflow counts")
        second = module._safe_replace_pattern("Workflow counts")
        assert first is not None
        assert second is first
        cache = module._safe_replace_pattern.cache_info()
        assert cache.misses == 1
        assert cache.hits == 1
        assert module._safe_replace(
            "Workflow counts remain visible.",
            "Workflow counts",
            "Los conteos de flujos de trabajo",
        ) == "Los conteos de flujos de trabajo remain visible."


def test_spanish_finding_register_localizes_prose_but_preserves_exact_source() -> None:
    register = {
        "code_findings": [
            {
                "finding_id": "NICO-FINDING-ABC123",
                "title": "Reduce complexity in build_production_release_manifest",
                "path": "nico/production_release_gate.py",
                "line": 179,
                "business_impact": "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.",
                "recommended_correction": (
                    "Decompose `build_production_release_manifest` around cohesive branch groups, "
                    "preserve behavior with characterization tests, and enforce cyclomatic complexity "
                    "at or below 30 on the exact remediation commit."
                ),
            }
        ]
    }
    localized = _localized_register(register)
    finding = localized["code_findings"][0]
    assert finding["title"].startswith("Reducir la complejidad en ")
    assert finding["path"] == "nico/production_release_gate.py"
    assert "La lógica ramificada concentrada" in finding["business_impact"]
    assert "bebaja" not in finding["recommended_correction"]


def test_spanish_manifest_and_approval_supplement_has_no_english_section_titles() -> None:
    canonical = {
        "report_language": "es-MX",
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "abc123",
            "run_id": "comprun_test",
            "evidence_ledger_id": "ledger_test",
            "generated_at": "2026-08-16T00:00:00Z",
            "report_language": "es-MX",
        },
    }
    pdf = _render_manifest_spanish(
        canonical,
        [{"artifact_type": "findings_csv", "filename": "findings.csv", "sha256": "deadbeef"}],
    )
    extracted = _pdf_text(pdf)
    normalized = _normalized_pdf_text(pdf)
    assert "Manifiesto de artefactos del cliente" in normalized
    assert "Registro de revisión humana y aprobación de artefactos exactos" in normalized
    assert "Client Artifact Manifest" not in extracted
    assert "Human Review and Exact-Artifact Approval Record" not in extracted


def test_spanish_toc_is_localized_and_preserves_page_numbers() -> None:
    pdf = _toc_page_spanish(
        nav,
        [("Canonical Technical Scorecard", 6), ("Client Artifact Manifest", 43)],
        44,
    )
    extracted = _pdf_text(pdf)
    assert "Índice" in extracted
    assert "Cuadro de puntuación técnica" in extracted
    assert "Manifiesto de artefactos del cliente" in extracted
    assert "Table of Contents" not in extracted


def test_spanish_premium_cover_uses_same_shell_with_localized_copy() -> None:
    canonical = {
        "report_language": "es-MX",
        "generated_at": "2026-08-16T00:00:00Z",
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "abc123",
            "report_language": "es-MX",
        },
        "assessment": {"technical_score": 93, "evidence_adjusted_score": 93},
        "canonical_findings": [
            {"title": "Reduce complexity in build_production_release_manifest"},
        ],
    }
    extracted = _pdf_text(_cover(canonical, spanish=True))
    assert "POSTURA EJECUTIVA" in extracted.upper()
    assert "ELEMENTOS PRIORITARIOS PARA REVISIÓN" in extracted
    assert "Reducir la complejidad en build_production_release_manifest" in extracted
    assert "EVIDENCE-BOUND ENGINEERING INTELLIGENCE" not in extracted
    assert "CLIENT DELIVERY" not in extracted
