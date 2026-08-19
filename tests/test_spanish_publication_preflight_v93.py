from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico.comprehensive_decision_content_restoration_v66 import (
    _synthesized_complexity_findings,
)
from nico.comprehensive_spanish_publication_preflight_v93 import (
    assert_spanish_publication_preflight,
    inspect_spanish_publication_preflight,
)


def test_current_generated_complexity_family_passes_one_complete_spanish_preflight() -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
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
    findings = _synthesized_complexity_findings(hotspots, commit_sha)
    prior = {
        "risk_reduction_and_executive_briefing": {
            "findings": findings,
        }
    }
    before = deepcopy(prior)

    manifest = inspect_spanish_publication_preflight(
        {"report_language": "es-MX"},
        prior,
    )

    assert manifest["status"] == "complete"
    assert manifest["spanish_requested"] is True
    assert manifest["failure_count"] == 0
    assert manifest["checked_presentation_values"] >= 20
    assert prior == before

    production_source = findings[0]["acceptance_criteria"][0]
    assert production_source == (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323."
    )
    translated = canonical._translate_presentation_field(
        production_source,
        "acceptance_criteria",
    )
    assert "La nueva ejecución sobre el SHA exacto" in translated
    assert "nico/comprehensive_review_work_v1.py:323" in translated


def test_preflight_reports_all_missing_contracts_in_one_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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
    prior = {
        "decision_report_generation": {
            "acceptance_criteria": ["Future untranslated acceptance sentence."],
            "rollback": "Future untranslated rollback sentence.",
            "recommendation": "Future untranslated recommendation sentence.",
        }
    }

    manifest = inspect_spanish_publication_preflight(
        {"requested_report_language": "es-MX"},
        prior,
    )

    assert manifest["status"] == "blocked"
    assert manifest["failure_count"] == 3
    assert len(manifest["failure_details"]) == 3
    assert {item["field"] for item in manifest["failure_details"]} == {
        "acceptance_criteria",
        "rollback",
        "recommendation",
    }
    assert all(item["path"].startswith("prior_stage_results.") for item in manifest["failure_details"])

    with pytest.raises(ValueError) as excinfo:
        assert_spanish_publication_preflight(
            {"requested_report_language": "es-MX"},
            prior,
        )
    message = str(excinfo.value)
    assert "spanish_presentation_preflight_failed:count=3" in message
    assert "acceptance_criteria" in message
    assert "rollback" in message
    assert "recommendation" in message


def test_preflight_does_not_touch_english_or_raw_machine_subtrees(monkeypatch: pytest.MonkeyPatch) -> None:
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

    english = inspect_spanish_publication_preflight(
        {"report_language": "en-US"},
        {"decision_report_generation": raw},
    )
    assert english["status"] == "not_applicable"
    assert calls == []

    spanish = inspect_spanish_publication_preflight(
        {"report_language": "es-MX"},
        {"decision_report_generation": raw},
    )
    assert spanish["status"] == "complete"
    assert spanish["checked_presentation_values"] == 0
    assert calls == []


def test_stable_v90_report_base_runs_preflight_before_artifact_generation() -> None:
    source = Path("nico/comprehensive_report_worker_runtime_v90.py").read_text(
        encoding="utf-8"
    )
    preflight = source.index(
        "spanish_preflight = assert_spanish_publication_preflight(context, prior)"
    )
    package = source.index("package = build_comprehensive_report_package(")

    assert preflight < package
    assert '"spanish_presentation_preflight": spanish_preflight' in source
    assert '"spanish_publication_preflight_bound": True' in source
