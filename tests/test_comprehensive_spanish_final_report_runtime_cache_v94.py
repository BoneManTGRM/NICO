from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
    reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests,
    spanish_final_report_runtime_cache_status,
)
from nico.comprehensive_spanish_publication_preflight_v93 import (
    assert_spanish_canonical_publication_preflight,
)


def _spanish_canonical() -> dict:
    return {
        "identity": {
            "run_id": "comprun_spanish_cache_v94",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_spanish_cache_v94",
            "report_language": "es-MX",
        },
        "report_language": "es-MX",
        "locale": "es-MX",
        "assessment": {
            "summary": "Proceed to human review; client delivery remains blocked.",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [
            {
                "stage_id": "risk_reduction_and_executive_briefing",
                "title": "Risk Reduction and Executive Briefing",
                "summary": "Proceed to human review; client delivery remains blocked.",
                "status": "complete",
            }
        ],
    }


def test_spanish_preflight_translation_is_reused_by_renderer() -> None:
    state = install_comprehensive_spanish_final_report_runtime_cache_v94()
    assert state["bound"] is True
    reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests()

    source = _spanish_canonical()
    manifest = assert_spanish_canonical_publication_preflight(source)
    assert manifest["status"] == "complete"

    translator = canonical._translate_presentation_field
    before = translator.cache_info()
    translated = translator(
        "Proceed to human review; client delivery remains blocked.",
        "summary",
    )
    after = translator.cache_info()

    assert translated == "Proceder a la revisión humana; la entrega al cliente permanece bloqueada."
    assert after.hits >= before.hits + 1
    assert spanish_final_report_runtime_cache_status()[
        "preflight_translation_results_reused_by_renderer"
    ] is True


def test_markdown_and_pdf_reuse_same_localized_canonical_projection() -> None:
    install_comprehensive_spanish_final_report_runtime_cache_v94()
    reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests()

    source = _spanish_canonical()
    original = deepcopy(source)
    first = canonical._render_inputs(source)
    second = canonical._render_inputs(source)
    state = spanish_final_report_runtime_cache_status()

    assert second is first
    assert source == original
    assert state["render_input_cache_entries"] == 1
    assert state["render_input_cache_hits"] >= 1
    assert state["render_input_cache_misses"] == 1
    assert state["markdown_pdf_localized_inputs_reused_for_same_canonical_object"] is True
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False


def test_production_bootstrap_installs_cache_after_terminal_authority() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    bootstrap = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert "nico.api.spanish_final_report_bootstrap:app" in dockerfile
    assert "from nico.api.terminal_authority_bootstrap import app" in bootstrap
    assert "install_comprehensive_spanish_final_report_runtime_cache_v94" in bootstrap
    assert "human_review_required" in bootstrap
    assert "client_delivery_allowed" in bootstrap
