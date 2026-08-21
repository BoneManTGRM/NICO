from __future__ import annotations

from pathlib import Path

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico.comprehensive_spanish_assessment_scope_v97 import (
    PRODUCTION_ASSESSMENT_SCOPE,
    PRODUCTION_ASSESSMENT_SCOPE_ES,
    UNKNOWN_ASSESSMENT_SCOPE_SENTINEL,
    install_comprehensive_spanish_assessment_scope_v97,
)
from nico.comprehensive_spanish_canonical_acceptance_normalization_v96 import (
    install_comprehensive_spanish_canonical_acceptance_normalization_v96,
)
from nico.comprehensive_spanish_canonical_evidence_literals_v95 import (
    install_comprehensive_spanish_canonical_evidence_literals_v95,
)
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)
from nico.comprehensive_spanish_publication_preflight_v93 import (
    inspect_spanish_canonical_publication_preflight,
    install_spanish_publication_preflight_v93,
)


def test_exact_production_assessment_scope_translates() -> None:
    state = install_comprehensive_spanish_assessment_scope_v97()

    assert state["bound"] is True
    assert state["production_assessment_scope_translation_supported"] is True
    assert state["approved_exact_contracts_only"] is True
    assert state["unknown_assessment_scope_contract_unregistered"] is True
    assert state["translator_replacement_performed"] is False

    translated = canonical._translate_presentation_field(
        PRODUCTION_ASSESSMENT_SCOPE,
        "assessment_scope",
    )
    assert translated == PRODUCTION_ASSESSMENT_SCOPE_ES
    assert canonical._looks_like_untranslated_english(translated) is False


def test_terminal_period_normalized_scope_translates_without_broadening() -> None:
    state = install_comprehensive_spanish_assessment_scope_v97()
    assert state["terminal_period_normalization_supported"] is True

    translated = canonical._translate_presentation_field(
        PRODUCTION_ASSESSMENT_SCOPE.removesuffix("."),
        "assessment_scope",
    )
    assert translated == PRODUCTION_ASSESSMENT_SCOPE_ES.removesuffix(".")


def test_unknown_assessment_scope_contract_is_not_registered() -> None:
    state = install_comprehensive_spanish_assessment_scope_v97()

    assert state["unknown_assessment_scope_contract_unregistered"] is True
    assert state["unknown_assessment_scope_prose_owned_by_existing_boundary"] is True
    assert (
        v88._translate_targeted_presentation_literal(
            UNKNOWN_ASSESSMENT_SCOPE_SENTINEL
        )
        is None
    )
    assert (
        UNKNOWN_ASSESSMENT_SCOPE_SENTINEL
        not in v88._TARGETED_PRESENTATION_TRANSLATIONS
    )
    assert (
        UNKNOWN_ASSESSMENT_SCOPE_SENTINEL.casefold()
        not in v88._TARGETED_PRESENTATION_TRANSLATIONS_CASEFOLD
    )


def test_full_worker_order_preflight_accepts_the_production_scope() -> None:
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    install_comprehensive_spanish_assessment_scope_v97()
    install_comprehensive_spanish_canonical_evidence_literals_v95()
    install_comprehensive_spanish_final_report_runtime_cache_v94()
    install_spanish_publication_preflight_v93()

    report = {
        "report_language": "es-MX",
        "identity": {"report_language": "es-MX"},
        "assessment": {
            "report_language": "es-MX",
            "assessment_scope": PRODUCTION_ASSESSMENT_SCOPE,
        },
    }
    manifest = inspect_spanish_canonical_publication_preflight(report)

    assert manifest["status"] == "complete"
    assert manifest["failure_count"] == 0
    assert manifest["spanish_requested"] is True


def test_both_production_bootstraps_bind_scope_before_the_render_cache() -> None:
    worker = Path("nico/api/final_report_worker_bootstrap.py").read_text(
        encoding="utf-8"
    )
    parent = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )

    worker_scope = worker.index(
        "install_comprehensive_spanish_assessment_scope_v97()"
    )
    worker_cache = worker.index(
        "install_comprehensive_spanish_final_report_runtime_cache_v94()"
    )
    parent_scope = parent.index(
        "install_comprehensive_spanish_assessment_scope_v97()"
    )
    parent_cache = parent.index(
        "install_comprehensive_spanish_final_report_runtime_cache_v94()"
    )

    assert worker_scope < worker_cache
    assert parent_scope < parent_cache
    assert "production_assessment_scope_translation_supported" in worker
    assert "production_assessment_scope_translation_supported" in parent
    assert "unknown_assessment_scope_contract_unregistered" in worker
    assert "unknown_assessment_scope_contract_unregistered" in parent


def test_temporary_diagnostic_workflow_is_removed_before_merge() -> None:
    assert not Path(
        ".github/workflows/temporary-detached-run-diagnostic.yml"
    ).exists()
