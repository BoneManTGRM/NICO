from __future__ import annotations

from copy import deepcopy

import pytest

from nico.client_finding_priority_calibration_v1 import calibrate_finding
from nico.client_finding_remediation_register_v3 import _specific_correction
from nico.comprehensive_decision_content_restoration_v66 import (
    _complexity_hotspots,
    _synthesized_complexity_findings,
)
from nico.comprehensive_spanish_canonical_acceptance_normalization_v96 import (
    install_comprehensive_spanish_canonical_acceptance_normalization_v96,
)
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_presentation_parity_v1 as presentation


@pytest.mark.parametrize("complexity", [29, 30, 31])
def test_inclusive_review_boundary_has_strict_closure_in_english_and_spanish(complexity: int) -> None:
    """Measured 30 must remain reviewable and must not already satisfy closure."""
    hotspot = {
        "path": "apps/web/app/AssessmentPanel.tsx",
        "line": 146,
        "end_line": 362,
        "name": "AssessmentPanel",
        "cyclomatic_complexity": complexity,
        "method": "typescript_compiler_ast",
    }
    stages = {"complexity": {"hotspots": [hotspot]}}
    original = deepcopy(stages)
    selected = _complexity_hotspots(stages)
    assert bool(selected) is (complexity >= 30)
    assert stages == original
    if complexity == 29:
        return

    finding = _synthesized_complexity_findings(selected, "a" * 40)[0]
    finding["human_disposition"] = {"status": "needs_more_evidence", "rationale": "pending source review"}
    original_finding = deepcopy(finding)
    calibrated = calibrate_finding(finding)
    assert calibrated["priority"] == "P2"
    assert calibrated["measured_cyclomatic_complexity"] == complexity
    assert "meets or exceeds the review threshold" in calibrated["priority_rationale"]
    assert calibrated["finding_id"] == finding["finding_id"]
    assert calibrated["human_disposition"] == finding["human_disposition"]
    assert finding == original_finding

    acceptance = finding["verification"][0]
    assert "complexity of 30 or greater" in acceptance
    assert "complexity below 30" in finding["recommendation"]
    corrected = _specific_correction(finding, "complexity_hotspot")
    assert "complexity below 30" in corrected

    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    for text, field, expected in (
        (acceptance, "acceptance_criteria", "igual o superior a 30"),
        (acceptance.rstrip("."), "acceptance_criteria", "igual o superior a 30"),
        (finding["recommendation"], "recommendation", "inferior a 30"),
        (corrected, "recommended_correction", "inferior a 30"),
    ):
        for translated in (
            canonical._translate_presentation_field(text, field),
            canonical._translate_presentation(text),
            presentation._safe_es(text),
        ):
            assert expected in translated
            assert "igual o inferior" not in translated
            assert "30 o menos" not in translated
            assert canonical._looks_like_untranslated_english(translated) is False
    assert finding == original_finding
