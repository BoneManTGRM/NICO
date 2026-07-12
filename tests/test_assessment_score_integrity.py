from __future__ import annotations

from pathlib import Path

import nico.full_assessment_scorecard as scorecard
import nico.hosted_assessment as hosted
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers
import nico.snapshot_repository_evidence as snapshot_repository
from nico.assessment_score_integrity import (
    INTEGRITY_VERSION,
    _built_in_secret_scan,
    _built_in_static_scan,
    analyze_javascript_functions,
    calibrated_collect_complexity_evidence,
    install_assessment_score_integrity,
)
from nico.assessment_score_integrity_compat import (
    calibrated_secrets_section,
    calibrated_static_section,
    deduplicated_secret_candidates as classify_secret_candidates,
    install_score_integrity_compatibility,
)


def _scanner(*results: dict) -> dict:
    run = [str(item.get("scanner")) for item in results if item.get("status") in {"passed", "failed", "error", "timeout"}]
    return {
        "status": "attached",
        "tools_requested": run,
        "tools_run": run,
        "unavailable_tools": [],
        "failed_tools": [str(item.get("scanner")) for item in results if item.get("status") in {"failed", "error"}],
        "timed_out_tools": [str(item.get("scanner")) for item in results if item.get("status") == "timeout"],
        "scanner_results": list(results),
    }


def _repo(secret_hits: int = 0, risk_hits: int = 0) -> dict:
    return {
        "code_signal_evidence": {
            "potential_secret_pattern_hits": secret_hits,
            "risk_pattern_hits": risk_hits,
        }
    }


def test_placeholder_and_detector_definitions_are_low_confidence() -> None:
    text = """
SECRET_PATTERNS = [re.compile(r'ghp_[A-Za-z0-9_]{20,}')]
API_KEY = 'example_replace_me_token_1234567890'
"""

    candidates = classify_secret_candidates("tests/fixtures/.env.example", text)

    assert candidates
    assert all(item["confidence"] == "low" for item in candidates)
    assert all("example_replace_me_token_1234567890" not in repr(item) for item in candidates)


def test_specific_non_example_token_is_high_confidence_and_masked() -> None:
    raw = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"

    candidates = classify_secret_candidates("nico/runtime_config.py", f"TOKEN = '{raw}'")
    specific = next(item for item in candidates if item["kind"] == "github_token")

    assert len(candidates) == 1
    assert specific["confidence"] == "high"
    assert raw not in repr(specific)
    assert specific["masked_preview"].startswith("ghp_")
    assert len(specific["fingerprint"]) == 16


def test_builtin_secret_scanner_never_returns_raw_values(tmp_path: Path) -> None:
    install_score_integrity_compatibility()
    raw = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    (tmp_path / "config.py").write_text(f"TOKEN = '{raw}'\n", encoding="utf-8")
    (tmp_path / "example.env").write_text("API_KEY=example_replace_me_123456789\n", encoding="utf-8")

    result = _built_in_secret_scan(tmp_path)

    assert result["status"] == "failed"
    assert result["finding_counts"]["high"] == 1
    assert raw not in result["safe_output_preview"]
    assert "fingerprint=" in result["safe_output_preview"]
    assert result["full_history_covered"] is False


def test_low_confidence_candidate_does_not_force_secrets_red() -> None:
    scanner = _scanner(
        {
            "scanner": "nico-secrets",
            "status": "passed",
            "finding_counts": {"high": 0, "medium": 0, "low": 1},
            "files_scanned": 100,
        }
    )

    section = calibrated_secrets_section(_repo(secret_hits=0), scanner)

    assert section["score"] >= 75
    assert section["status"] in {"yellow", "green"}
    assert section["confidence"] == "current-tree-scanner-bound"
    assert any("full git-history" in note.lower() for note in section["unavailable"])


def test_high_confidence_candidate_remains_red() -> None:
    scanner = _scanner(
        {
            "scanner": "nico-secrets",
            "status": "failed",
            "finding_counts": {"high": 1, "medium": 0, "low": 0},
            "files_scanned": 100,
        }
    )

    section = calibrated_secrets_section(_repo(secret_hits=1), scanner)

    assert section["score"] <= 44
    assert section["status"] == "red"
    assert section["findings"]


def test_builtin_static_scanner_ignores_clean_source_and_scores_current_tree_coverage(tmp_path: Path) -> None:
    install_score_integrity_compatibility()
    (tmp_path / "safe.py").write_text("def add(left, right):\n    return left + right\n", encoding="utf-8")

    result = _built_in_static_scan(tmp_path)
    section = calibrated_static_section(_repo(risk_hits=0), _scanner(result))

    assert result["status"] == "passed"
    assert result["finding_count"] == 0
    assert section["score"] >= 70
    assert section["confidence"] == "current-tree-scanner-bound"


def test_builtin_static_scanner_excludes_test_only_risk_fixtures(tmp_path: Path) -> None:
    install_score_integrity_compatibility()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unsafe.py").write_text("import os\nos.system(user_input)\n", encoding="utf-8")
    (tmp_path / "safe.py").write_text("def safe(value):\n    return value\n", encoding="utf-8")

    result = _built_in_static_scan(tmp_path)

    assert result["status"] == "passed"
    assert result["finding_count"] == 0
    assert result["files_scanned"] == 1


def test_builtin_static_scanner_retains_material_findings(tmp_path: Path) -> None:
    install_score_integrity_compatibility()
    (tmp_path / "unsafe.py").write_text("import os\nos.system(user_input)\n", encoding="utf-8")

    result = _built_in_static_scan(tmp_path)
    section = calibrated_static_section(_repo(risk_hits=1), _scanner(result))

    assert result["status"] == "failed"
    assert result["finding_count"] >= 1
    assert section["score"] < 70
    assert section["findings"]


def test_javascript_complexity_uses_function_units_not_one_whole_file() -> None:
    text = """
export function choose(value: number) {
  if (value > 10) return value
  return 0
}
const mapValue = (value: number) => {
  if (value < 0) return 0
  return value ? value + 1 : 1
}
class Service {
  async load(active: boolean) {
    if (active) {
      return await Promise.resolve(1)
    }
    return 0
  }
}
"""

    result = analyze_javascript_functions("apps/web/example.ts", text)
    units = result["functions"]

    assert result["method"] == "function_level_lexical_v2"
    assert result["declared_function_count"] >= 3
    assert len(units) >= 3
    assert all(item["name"] != "<module-heuristic>" for item in units)
    assert max(int(item["cyclomatic_complexity"]) for item in units) < 10


def test_calibrated_complexity_reports_v2_and_more_units_than_files() -> None:
    install_assessment_score_integrity()
    install_score_integrity_compatibility()
    files = {
        "apps/web/example.ts": """
export function one(value: number) { if (value) return 1; return 0 }
export function two(value: number) { if (value > 2) return 2; return 0 }
export function three(value: number) { return value ? 3 : 0 }
""",
        "nico/simple.py": "def simple(value):\n    return value + 1\n",
    }

    result = calibrated_collect_complexity_evidence(files)

    assert result["status"] == "attached"
    assert result["analyzer_version"] == "nico-bounded-complexity-v2"
    assert result["javascript_typescript_method"] == "function_level_lexical_v2"
    assert result["functions_measured"] > result["files_analyzed"]
    assert result["maximum_cyclomatic_complexity"] < 10
    assert any("function-level lexical extraction" in note for note in result["unavailable_data_notes"])


def test_installer_rebinds_scoring_collection_and_mid_attachment() -> None:
    first = install_assessment_score_integrity()
    second = install_assessment_score_integrity()
    compat_first = install_score_integrity_compatibility()
    compat_second = install_score_integrity_compatibility()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert compat_first["status"] in {"installed", "already_installed"}
    assert compat_second["status"] == "already_installed"
    assert first["version"] == INTEGRITY_VERSION
    assert "nico-secrets" in scanner_worker.TOOL_CATALOG
    assert "nico-static" in scanner_worker.TOOL_CATALOG
    assert hosted.scan_files.__name__ == "calibrated_scan_files"
    assert hosted.analyze_secrets.__name__ == "calibrated_analyze_secrets"
    assert snapshot_repository.scan_files.__name__ == "calibrated_scan_files"
    assert snapshot_repository.collect_complexity_evidence.__name__ == "calibrated_collect_complexity_evidence"
    assert scorecard._secrets_section.__name__ == "calibrated_secrets_section"
    assert scorecard._static_section.__name__ == "calibrated_static_section"
    assert snapshot_handlers._snapshot_evidence_attachment_handler.__name__ == "calibrated_attachment_handler"
    assert mid_handlers._snapshot_evidence_attachment_handler.__name__ == "calibrated_attachment_handler"
