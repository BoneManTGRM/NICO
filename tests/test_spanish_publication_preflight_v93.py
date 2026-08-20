from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico.comprehensive_decision_content_restoration_v66 import restore_decision_content
from nico.comprehensive_spanish_publication_preflight_v93 import (
    assert_spanish_canonical_publication_preflight,
    inspect_spanish_canonical_publication_preflight,
)


def _restored_complexity_canonical() -> tuple[dict, dict]:
    commit_sha = "b" * 40
    hotspots = [
        {
            "path": "nico/comprehensive_review_work_v1.py",
            "line": 323,
            "name": "review_work",
            "cyclomatic_complexity": 47,
        },
        {
            "path": "nico/reporting.py",
            "line": 101,
            "name": "build_report",
            "cyclomatic_complexity": 44,
        },
        {
            "path": "nico/collector.py",
            "line": 202,
            "name": "collect_snapshot",
            "cyclomatic_complexity": 45,
        },
        {
            "path": "scripts/scan.py",
            "line": 303,
            "name": "main",
            "cyclomatic_complexity": 46,
        },
    ]
    raw_stages = {
        "ci_cd_architecture_complexity_velocity": {
            "hotspots": hotspots,
        }
    }
    base = {
        "report_language": "es-MX",
        "locale": "es-MX",
        "identity": {
            "report_language": "es-MX",
            "commit_sha": commit_sha,
        },
        "assessment": {
            "report_language": "es-MX",
            "locale": "es-MX",
        },
    }
    output, _, _ = restore_decision_content(
        base,
        raw_stages=raw_stages,
        assessment=base["assessment"],
        commit_sha=commit_sha,
    )
    return output, raw_stages


def test_current_generated_complexity_family_is_preflighted_after_restoration() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    restored, raw_stages = _restored_complexity_canonical()
    before = deepcopy(restored)

    # The incident string does not exist in raw retained stage state. It is created by
    # restoration, which is why a preflight before canonical construction is insufficient.
    raw_text = repr(raw_stages)
    assert "The exact-SHA rerun no longer reports cyclomatic complexity above" not in raw_text

    findings = restored["findings_register"]
    production_source = next(
        item["acceptance_criteria"][0]
        for item in findings
        if item.get("path") == "nico/comprehensive_review_work_v1.py"
    )
    assert production_source == (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323."
    )

    manifest = inspect_spanish_canonical_publication_preflight(restored)
    assert manifest["status"] == "complete"
    assert manifest["spanish_requested"] is True
    assert manifest["canonical_restoration_complete"] is True
    assert manifest["failure_count"] == 0
    assert manifest["checked_presentation_values"] >= 20
    assert restored == before

    translated = canonical._translate_presentation_field(
        production_source,
        "acceptance_criteria",
    )
    assert "La nueva ejecución sobre el SHA exacto" in translated
    assert "nico/comprehensive_review_work_v1.py:323" in translated


def test_preflight_reports_all_missing_restored_contracts_in_one_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = {
        "Future untranslated acceptance sentence.",
        "Future untranslated rollback sentence.",
        "Future untranslated recommendation sentence.",
    }

    def translator(value: str, key: str) -> str:
        if value in missing:
            raise ValueError(f"missing Spanish presentation translation for {key}: {value}")
        return value

    monkeypatch.setattr(canonical, "_translate_presentation_field", translator)
    restored = {
        "report_language": "es-MX",
        "identity": {"report_language": "es-MX"},
        "findings_register": [
            {
                "acceptance_criteria": ["Future untranslated acceptance sentence."],
                "rollback": "Future untranslated rollback sentence.",
                "recommendation": "Future untranslated recommendation sentence.",
            }
        ],
    }

    manifest = inspect_spanish_canonical_publication_preflight(restored)
    assert manifest["status"] == "blocked"
    assert manifest["failure_count"] == 3
    assert len(manifest["failure_details"]) == 3
    assert {item["field"] for item in manifest["failure_details"]} == {
        "acceptance_criteria",
        "rollback",
        "recommendation",
    }
    assert all(
        item["path"].startswith("canonical_report.findings_register")
        for item in manifest["failure_details"]
    )

    with pytest.raises(ValueError) as excinfo:
        assert_spanish_canonical_publication_preflight(restored)
    message = str(excinfo.value)
    assert "spanish_presentation_preflight_failed:count=3" in message
    assert "acceptance_criteria" in message
    assert "rollback" in message
    assert "recommendation" in message


def test_preflight_does_not_touch_english_or_raw_machine_subtrees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def translator(value: str, key: str) -> str:
        calls.append((value, key))
        return value

    monkeypatch.setattr(canonical, "_translate_presentation_field", translator)
    raw = {
        "scanner": {
            "recommendation": "Raw scanner payload that is not presentation copy.",
        },
        "canonical_findings": [
            {"acceptance_criteria": "Raw canonical finding remains immutable."},
        ],
    }

    english = inspect_spanish_canonical_publication_preflight(
        {"report_language": "en-US", **raw}
    )
    assert english["status"] == "not_applicable"
    assert calls == []

    spanish = inspect_spanish_canonical_publication_preflight(
        {"report_language": "es-MX", "identity": {"report_language": "es-MX"}, **raw}
    )
    assert spanish["status"] == "complete"
    assert spanish["checked_presentation_values"] == 0
    assert calls == []


def test_canonical_source_preflights_after_restoration_and_before_hash_render() -> None:
    source = Path("nico/comprehensive_canonical_report_source_v1.py").read_text(
        encoding="utf-8"
    )
    restore = source.index("canonical, assessment, decision_content_restoration = restore_decision_content(")
    reconcile = source.index("canonical, finding_count_truth = reconcile_finding_count_truth(canonical)")
    preflight = source.index("assert_spanish_canonical_publication_preflight(canonical)")
    report_render = source.index("report_content_render = install_comprehensive_report_content_render_v66()")
    truth_hash = source.index("truth_sha = _canonical_hash(canonical)")

    assert restore < reconcile < preflight < report_render < truth_hash


def test_v90_worker_is_not_used_as_a_pre_restoration_translation_scanner() -> None:
    source = Path("nico/comprehensive_report_worker_runtime_v90.py").read_text(
        encoding="utf-8"
    )
    assert "assert_spanish_publication_preflight" not in source
    assert "spanish_presentation_preflight" not in source
