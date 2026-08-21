from __future__ import annotations

from pathlib import Path

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_spanish_canonical_evidence_literals_v95 import (
    install_comprehensive_spanish_canonical_evidence_literals_v95,
    serialized_canonical_evidence_literal,
)


INCIDENT_EVIDENCE = (
    "technical_analysis.activity.sample_pull_requests[1].title: "
    "Isolate Spanish production proof lifecycle and require it for release",
    "scanner_triage.finding_summary.truth_model: dependency materiality requires "
    "advisory, installed package/version, fixed version, dependency path, verified "
    "production scope, and verified reachability",
    "scanner.finding_summary.truth_model: dependency materiality requires advisory, "
    "installed package/version, fixed version, dependency path, verified production "
    "scope, and verified reachability",
    "snapshot.commit_message: Fix Spanish final-report detached worker failure (#1255)",
)


def test_incident_canonical_evidence_is_recognized_as_exact_machine_truth() -> None:
    for value in INCIDENT_EVIDENCE:
        assert serialized_canonical_evidence_literal(value, "evidence") is True


def test_guard_preserves_incident_evidence_byte_for_byte() -> None:
    state = install_comprehensive_spanish_canonical_evidence_literals_v95()
    assert state["bound"] is True
    assert state["canonical_evidence_byte_preserving"] is True
    assert state["report_owned_presentation_prose_still_fail_closed"] is True

    for value in INCIDENT_EVIDENCE:
        assert canonical._translate_presentation_field(value, "evidence") == value


def test_guard_does_not_exempt_report_owned_flattened_presentation_prose() -> None:
    install_comprehensive_spanish_canonical_evidence_literals_v95()
    value = (
        "assessment.summary: Future untranslated presentation sentence requires human "
        "review and remains blocked before delivery."
    )
    assert serialized_canonical_evidence_literal(value, "evidence") is False
    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        canonical._translate_presentation_field(value, "evidence")


def test_guard_does_not_exempt_freeform_untranslated_evidence_prose() -> None:
    install_comprehensive_spanish_canonical_evidence_literals_v95()
    value = "Future untranslated evidence sentence requires review and remains blocked."
    assert serialized_canonical_evidence_literal(value, "evidence") is False
    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        canonical._translate_presentation_field(value, "evidence")


def test_title_exemption_is_limited_to_remote_repository_provenance() -> None:
    remote = (
        "technical_analysis.activity.sample_pull_requests[9].title: "
        "Preserve scanner truth from presentation policy and fix pipeline (REPARO-028)"
    )
    report_owned = (
        "assessment.report_sections[0].title: "
        "Future untranslated title requires review before delivery"
    )
    assert serialized_canonical_evidence_literal(remote, "evidence") is True
    assert serialized_canonical_evidence_literal(report_owned, "evidence") is False


def test_non_evidence_fields_never_use_flattened_machine_literal_exemption() -> None:
    value = "snapshot.commit_message: Fix Spanish final-report detached worker failure (#1255)"
    assert serialized_canonical_evidence_literal(value, "summary") is False


def test_worker_installs_evidence_guard_before_runtime_cache() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")
    guard = source.index("install_comprehensive_spanish_canonical_evidence_literals_v95()")
    cache = source.index("install_comprehensive_spanish_final_report_runtime_cache_v94()")
    assert guard < cache
    assert "presentation_prose_still_fail_closed" in source
    assert "canonical_evidence_literals_preserved" in source
