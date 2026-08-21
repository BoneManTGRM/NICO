from __future__ import annotations

from pathlib import Path

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
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
from nico.v2_assessment_pipeline import canonicalize_findings


PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD = (
    "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
    "nico/comprehensive_review_work_v1.py:323"
)
PRODUCTION_ACCEPTANCE_WITH_PERIOD = PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD + "."

CANONICALLY_NORMALIZED_ACCEPTANCE_CONTRACTS = (
    PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD,
    "Targeted characterization tests pass on the remediation commit",
    "The repository's complete required-check suite passes on the remediation commit",
    "No new material regression or cross-format report-truth mismatch is introduced",
    "All verification requirements pass on the exact remediation commit",
    "The exact-SHA rerun no longer reports the condition as unresolved material risk",
    "No new material regression is introduced",
)


def test_canonical_dedup_reproduces_production_terminal_period_loss() -> None:
    common = {
        "finding_id": "NICO-FINDING-PUNCTUATION-REGRESSION",
        "id": "NICO-FINDING-PUNCTUATION-REGRESSION",
        "category": "architecture",
        "finding_family": "complexity_hotspot",
        "location": "nico/comprehensive_review_work_v1.py:323",
        "symbol": "review_work",
        "title": "Reduce complexity in review_work",
        "recommendation": "Decompose the bounded unit and rerun exact-SHA verification.",
    }
    punctuated = {
        **common,
        "acceptance_criteria": [PRODUCTION_ACCEPTANCE_WITH_PERIOD],
    }
    normalized = {
        **common,
        "acceptance_criteria": [PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD],
    }

    findings = canonicalize_findings([punctuated, normalized])
    assert len(findings) == 1
    assert findings[0]["acceptance_criteria"] == [PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD]


def test_production_complexity_acceptance_without_period_translates() -> None:
    state = install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    assert state["bound"] is True
    assert state["production_complexity_acceptance_without_period_supported"] is True
    assert state["approved_contracts_only"] is True

    translated = canonical._translate_presentation_field(
        PRODUCTION_ACCEPTANCE_WITHOUT_PERIOD,
        "acceptance_criteria",
    )
    assert translated == (
        "La nueva ejecución sobre el SHA exacto ya no informa una complejidad "
        "ciclomática superior a 30 en nico/comprehensive_review_work_v1.py:323."
    )


def test_all_known_acceptance_contracts_survive_terminal_period_normalization() -> None:
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    for value in CANONICALLY_NORMALIZED_ACCEPTANCE_CONTRACTS:
        translated = canonical._translate_presentation_field(value, "acceptance_criteria")
        assert translated != value
        assert canonical._looks_like_untranslated_english(translated) is False


def test_unknown_acceptance_prose_remains_fail_closed() -> None:
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    unknown = (
        "Future untranslated acceptance criterion requires review and remains blocked "
        "before client delivery"
    )
    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        canonical._translate_presentation_field(unknown, "acceptance_criteria")


def test_full_worker_order_preflight_accepts_production_normalized_contracts() -> None:
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    install_comprehensive_spanish_canonical_evidence_literals_v95()
    install_comprehensive_spanish_final_report_runtime_cache_v94()
    install_spanish_publication_preflight_v93()

    report = {
        "report_language": "es-MX",
        "identity": {"report_language": "es-MX"},
        "assessment": {"report_language": "es-MX"},
        "findings_register": [
            {
                "finding_id": "NICO-FINDING-PRODUCTION-REGRESSION",
                "acceptance_criteria": list(CANONICALLY_NORMALIZED_ACCEPTANCE_CONTRACTS),
            }
        ],
    }
    manifest = inspect_spanish_canonical_publication_preflight(report)
    assert manifest["status"] == "complete"
    assert manifest["failure_count"] == 0
    assert manifest["spanish_requested"] is True


def test_final_report_worker_installs_v96_before_v95_and_v94() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")
    v96 = source.index("install_comprehensive_spanish_canonical_acceptance_normalization_v96()")
    v95 = source.index("install_comprehensive_spanish_canonical_evidence_literals_v95()")
    v94 = source.index("install_comprehensive_spanish_final_report_runtime_cache_v94()")
    assert v96 < v95 < v94
    assert "canonical_acceptance_terminal_period_loss_supported" in source
    assert "unknown_presentation_prose_still_fail_closed" in source
