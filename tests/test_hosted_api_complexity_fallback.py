from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from nico.complexity_artifact_integration import attach_complexity_artifact_to_report
from nico.hosted_api_complexity_fallback import (
    attach_api_sample_complexity,
    build_api_sample_complexity_profile,
    fetch_repository_profile_with_complexity,
    select_balanced_profile_paths,
)
from nico.report_evidence_consistency_gate import apply_report_evidence_consistency_gate


ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "assessment_score_integrity_compat.py"
FALLBACK = ROOT / "nico" / "hosted_api_complexity_fallback.py"


def _section(section_id: str, score: int) -> dict[str, Any]:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "green" if score >= 80 else "yellow",
        "summary": section_id,
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def _source_files() -> dict[str, str]:
    return {
        "nico/service.py": (
            "def route(value):\n"
            "    if value > 10:\n"
            "        return value * 2\n"
            "    return value\n\n"
            "def second(items):\n"
            "    return [item for item in items if item]\n"
        ),
        "apps/web/app/page.tsx": (
            "export function Page({ ready }: { ready: boolean }) {\n"
            "  if (ready) { return <main>Ready</main>; }\n"
            "  return <main>Pending</main>;\n"
            "}\n"
        ),
        "scripts/check.py": "def check(value):\n    return bool(value)\n",
        "requirements.txt": "fastapi==0.116.0\npytest==8.4.0\n",
        "apps/web/package.json": '{"dependencies":{"next":"15.4.0"},"devDependencies":{"typescript":"5.8.0"}}',
    }


def test_balanced_profile_selection_reserves_production_source_files() -> None:
    tree = [
        {"type": "blob", "path": "README.md", "size": 100},
        {"type": "blob", "path": "package.json", "size": 100},
    ]
    tree.extend({"type": "blob", "path": f"docs/note-{index:03}.md", "size": 100} for index in range(100))
    tree.extend({"type": "blob", "path": f"nico/module_{index:03}.py", "size": 100} for index in range(20))
    tree.extend({"type": "blob", "path": f"apps/web/app/page_{index:03}.tsx", "size": 100} for index in range(20))
    tree.extend({"type": "blob", "path": f"services/api_{index:03}.ts", "size": 100} for index in range(20))

    selected = select_balanced_profile_paths(tree, max_files=20, source_reserve=12)
    sources = [path for path in selected if path.endswith((".py", ".js", ".jsx", ".ts", ".tsx"))]

    assert len(selected) == 20
    assert selected[:2] == ["README.md", "package.json"]
    assert len(sources) >= 12
    assert any(path.startswith("nico/") for path in sources)
    assert any(path.startswith("apps/") for path in sources)
    assert any(path.startswith("services/") for path in sources)
    assert not any("tests/" in path for path in sources)


def test_api_sample_complexity_produces_positive_bounded_metrics() -> None:
    profile = build_api_sample_complexity_profile(
        _source_files(),
        commit_sha="a" * 40,
        total_source_paths=640,
    )

    assert profile["source"] == "github_api_exact_commit_bounded_sample"
    assert profile["commit_sha"] == "a" * 40
    assert profile["source_file_count"] == 640
    assert profile["analyzed_file_count"] == 3
    assert profile["total_loc"] > 0
    assert profile["total_functions"] > 0
    assert profile["risk_level"] in {"low", "medium", "high"}
    assert profile["risk_level"] != "review_required"
    assert profile["manifest_dependency_count"] == 4
    assert any("bounded exact-commit GitHub API sample" in profile["guardrail"] for _ in [0])
    assert any("Git churn and ownership concentration" in item for item in profile["unavailable"])
    assert profile["human_review_required"] is True


def test_valid_api_sample_prevents_false_zero_complexity_cap() -> None:
    profile = build_api_sample_complexity_profile(
        _source_files(),
        commit_sha="b" * 40,
        total_source_paths=640,
    )
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-14T00:30:00Z",
        "maturity_signal": {"level": "Senior", "score": 86},
        "sections": [
            _section("code_audit", 86),
            _section("architecture_debt", 86),
            _section("velocity_complexity", 84),
        ],
    }

    result = attach_api_sample_complexity(result, profile)
    result = attach_complexity_artifact_to_report(result)
    result = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in result["sections"]}

    assert result["complexity_artifact"]["status"] == "completed"
    assert result["complexity_artifact"]["verified_for_this_report"] is True
    assert result["complexity_artifact"]["source"] == "github_api_exact_commit_bounded_sample"
    assert result["report_quality_guards"]["cross_tier_complexity_consistency"]["status"] == "verified"
    assert sections["velocity_complexity"]["score"] == 84
    assert sections["velocity_complexity"]["status"] == "green"
    assert not any("analyzed_files=0" in str(item) for item in sections["velocity_complexity"]["evidence"])
    assert any("Complexity evidence scope" in str(item) for item in sections["velocity_complexity"]["evidence"])


def test_zero_measurement_profile_is_not_presented_as_completed() -> None:
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-14T00:30:00Z",
        "complexity_engine": {
            "source_file_count": 640,
            "analyzed_file_count": 0,
            "total_loc": 0,
            "total_functions": 0,
            "complexity_score": 0,
            "velocity_score": 0,
            "risk_level": "review_required",
        },
        "sections": [_section("architecture_debt", 90), _section("velocity_complexity", 90)],
    }

    output = attach_complexity_artifact_to_report(result)
    sections = {item["id"]: item for item in output["sections"]}

    assert output["complexity_artifact"]["status"] == "unavailable"
    assert output["complexity_artifact"]["verified_for_this_report"] is False
    assert not any("artifact completed" in str(item).lower() for item in sections["velocity_complexity"]["evidence"])
    assert any("analyzed_files=0" in str(item) for item in sections["velocity_complexity"]["unavailable"])


class _FakeClient:
    def __init__(self) -> None:
        self.commit_sha = "c" * 40
        self.files = _source_files()
        self.files.update({f"docs/note-{index:03}.md": f"note {index}" for index in range(100)})
        self.tree = [
            {"type": "blob", "path": path, "size": len(text.encode("utf-8"))}
            for path, text in self.files.items()
        ]

    def repo_url(self, repository: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repository}{path}"

    def get_tree(self, repository: str, ref: str):
        assert repository == "BoneManTGRM/NICO"
        assert ref == self.commit_sha
        return list(self.tree), None

    def get_json(self, url: str, params: dict[str, Any] | None = None):
        if "/commits/" in url:
            return {"sha": self.commit_sha}, None
        if url.endswith("/contents"):
            return [{"name": "nico"}, {"name": "apps"}, {"name": "README.md"}], None
        marker = "/contents/"
        if marker in url:
            path = url.split(marker, 1)[1]
            text = self.files.get(path)
            if text is None:
                return None, "not found"
            return {
                "type": "file",
                "size": len(text.encode("utf-8")),
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            }, None
        return None, "unsupported"


def test_repository_profile_uses_one_exact_commit_and_balanced_source_sample() -> None:
    client = _FakeClient()

    profile = fetch_repository_profile_with_complexity(
        client,
        "BoneManTGRM/NICO",
        {"default_branch": "main"},
    )

    assert profile["snapshot_commit_sha"] == client.commit_sha
    assert profile["complexity_profile"]["commit_sha"] == client.commit_sha
    assert profile["complexity_profile"]["analyzed_file_count"] == 3
    assert profile["complexity_profile"]["total_functions"] > 0
    assert {"nico/service.py", "apps/web/app/page.tsx", "scripts/check.py"} <= set(profile["files"])
    assert len(profile["files"]) <= 90


def test_production_compat_installs_the_fallback() -> None:
    source = COMPAT.read_text(encoding="utf-8")

    assert "from nico.hosted_api_complexity_fallback import install_hosted_api_complexity_fallback" in source
    assert "complexity_fallback = install_hosted_api_complexity_fallback()" in source
    assert '"hosted_api_complexity_fallback"' in source


def test_fallback_scopes_profile_replacement_to_one_express_request() -> None:
    source = FALLBACK.read_text(encoding="utf-8")

    assert "with _PROFILE_PATCH_LOCK:" in source
    assert "previous_fetch = hosted.fetch_repository_profile" in source
    assert "hosted.fetch_repository_profile = fetch_repository_profile_with_complexity" in source
    assert "hosted.fetch_repository_profile = previous_fetch" in source
    assert "hosted.fetch_repository_profile = fetch_repository_profile_with_complexity\n\n    def" not in source
