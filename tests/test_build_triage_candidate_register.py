from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_triage_candidate_register.py"
spec = importlib.util.spec_from_file_location("build_triage_candidate_register", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TARGET_SHA = "9c876ba4e3e9bb152de52567232038e52a6bbb3e"


def _git_item(*, path: str, line: int, commit: str, raw: str, detector: str = "Postgres") -> dict:
    return {
        "DetectorName": detector,
        "Verified": False,
        "Raw": raw,
        "RawV2": raw,
        "Redacted": "",
        "SourceMetadata": {"Data": {"Git": {"file": path, "line": line, "commit": commit}}},
    }


def _run() -> dict:
    gitleaks = [
        {
            "RuleID": "generic-api-key",
            "File": f"tests/test_secret_{index}.py",
            "StartLine": index + 1,
            "Commit": f"g{index:039d}",
            "Secret": "must-never-appear",
            "Match": "must-never-appear",
        }
        for index in range(6)
    ]
    trufflehog = [
        _git_item(path="tests/a.py", line=1, commit="a" * 40, raw="one"),
        _git_item(path="tests/a.py", line=1, commit="a" * 40, raw="one"),
        _git_item(path="tests/b.py", line=2, commit="b" * 40, raw="two"),
        _git_item(path="tests/b.py", line=2, commit="b" * 40, raw="two"),
        _git_item(path="tests/c.py", line=3, commit="c" * 40, raw="three"),
        _git_item(path="tests/c.py", line=3, commit="c" * 40, raw="three"),
        _git_item(path="tests/c.py", line=3, commit="c" * 40, raw="three"),
    ]
    trufflehog.extend(
        _git_item(
            path=f"tests/unique_{index}.py",
            line=10 + index,
            commit=f"{index + 1:040d}",
            raw=f"value-{index}",
            detector="URI" if index % 2 else "Postgres",
        )
        for index in range(8)
    )
    trufflehog.append(_git_item(path=".env.example", line=23, commit="e" * 40, raw="example-only"))
    return {
        "deterministic_fingerprints": {"gitleaks": "1" * 64, "trufflehog": "2" * 64},
        "tools": {
            "gitleaks": {"findings": gitleaks, "findings_count": len(gitleaks)},
            "trufflehog": {"findings": trufflehog, "findings_count": len(trufflehog)},
        },
    }


def test_secret_population_reconciles_to_17_without_exposing_values() -> None:
    candidates, excluded = module._secret_candidates(_run(), TARGET_SHA)

    assert len(candidates) == 17
    assert len(excluded) == 5
    assert {item["reason"] for item in excluded} == {
        "exact_duplicate_scanner_observation",
        "unverified_example_template_observation",
    }
    assert all(item["human_review_required"] is True for item in candidates)
    assert all(item["human_approved"] is False for item in candidates)
    assert all(item["secret_material_omitted"] is True for item in candidates)
    serialized = json.dumps({"candidates": candidates, "excluded": excluded})
    for sensitive in ("must-never-appear", "example-only", "value-0", "one", "two", "three"):
        assert sensitive not in serialized


def test_secret_dedupe_fails_closed_for_distinct_values_at_one_safe_location() -> None:
    run = _run()
    first = run["tools"]["trufflehog"]["findings"][0]
    conflicting = json.loads(json.dumps(first))
    conflicting["Raw"] = "different-sensitive-value"
    conflicting["RawV2"] = "different-sensitive-value"
    run["tools"]["trufflehog"]["findings"].append(conflicting)

    with pytest.raises(ValueError, match="Multiple distinct secret values"):
        module._secret_candidates(run, TARGET_SHA)


def test_repository_path_is_stable_and_workspace_independent() -> None:
    observed = module._normal_path(
        "/home/runner/work/NICO/NICO/runner/frozen-scanner-proof/workspace-1/repo/requirements.txt"
    )
    assert observed == "requirements.txt"
