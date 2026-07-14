from __future__ import annotations

import base64
from typing import Any

import nico.complexity_artifact_integration as complexity_integration
import nico.hosted_api_complexity_fallback_compat as compat


class _BudgetClient:
    def __init__(self, successful_source_fetches: int) -> None:
        self.commit_sha = "d" * 40
        self.successful_source_fetches = successful_source_fetches
        self.source_requests = 0
        self.files = {
            "nico/alpha.py": "def alpha(value):\n    return value + 1\n",
            "nico/beta.py": "def beta(value):\n    return value * 2\n",
            "apps/web/app/a.ts": "export function a(value: number) { return value + 1; }\n",
            "apps/web/app/b.ts": "export function b(value: number) { return value + 2; }\n",
            "scripts/one.py": "def one():\n    return 1\n",
            "scripts/two.py": "def two():\n    return 2\n",
            "services/a.ts": "export function serviceA() { return true; }\n",
            "services/b.ts": "export function serviceB() { return false; }\n",
            "README.md": "# NICO\n",
            "requirements.txt": "fastapi==0.116.0\n",
        }
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
        if marker not in url:
            return None, "unsupported"
        path = url.split(marker, 1)[1]
        text = self.files.get(path)
        if text is None:
            return None, "not found"
        if compat.fallback._eligible_source_path(path):
            self.source_requests += 1
            if self.source_requests > self.successful_source_fetches:
                return None, "GitHub returned 403: API rate limit exceeded"
        return {
            "type": "file",
            "size": len(text.encode("utf-8")),
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        }, None


def _section(section_id: str) -> dict[str, Any]:
    return {
        "id": section_id,
        "label": section_id,
        "score": 89,
        "status": "green",
        "summary": section_id,
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def test_budget_aware_selection_bootstraps_source_before_manifests() -> None:
    client = _BudgetClient(successful_source_fetches=8)

    selected = compat.select_budget_aware_profile_paths(
        client.tree,
        max_files=10,
        source_reserve=8,
        source_bootstrap=4,
    )

    assert len(selected) == 10
    assert all(compat.fallback._eligible_source_path(path) for path in selected[:4])
    assert {path.split("/", 1)[0] for path in selected[:4]} >= {"apps", "nico", "scripts", "services"}
    assert "README.md" in selected[4:]
    assert "requirements.txt" in selected[4:]


def test_limited_api_budget_still_produces_positive_complexity_metrics() -> None:
    client = _BudgetClient(successful_source_fetches=4)

    result = compat.fetch_repository_profile_with_budget_provenance(
        client,
        "BoneManTGRM/NICO",
        {"default_branch": "main"},
    )
    profile = result["complexity_profile"]
    provenance = profile["fetch_provenance"]

    assert profile["commit_sha"] == client.commit_sha
    assert profile["analyzed_file_count"] == 4
    assert profile["total_loc"] > 0
    assert profile["total_functions"] > 0
    assert profile["risk_level"] != "review_required"
    assert provenance["source_paths_fetched"] == 4
    assert provenance["source_fetch_failure_count"] > 0
    assert provenance["source_fetch_failures"]


def test_zero_source_budget_is_retained_as_report_unavailable_evidence(monkeypatch) -> None:
    client = _BudgetClient(successful_source_fetches=0)
    profile = compat.fetch_repository_profile_with_budget_provenance(
        client,
        "BoneManTGRM/NICO",
        {"default_branch": "main"},
    )["complexity_profile"]
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-14T09:52:41Z",
        "complexity_engine": {
            "source_file_count": 650,
            "analyzed_file_count": 0,
            "total_loc": 0,
            "total_functions": 0,
            "risk_level": "review_required",
        },
        "sections": [_section("architecture_debt"), _section("velocity_complexity")],
    }

    monkeypatch.setattr(
        complexity_integration,
        "_nico_complexity_unavailable_detail_bridge",
        False,
        raising=False,
    )
    compat._install_unavailable_detail_bridge()
    output = compat.attach_api_sample_complexity_with_provenance(result, profile)
    output = complexity_integration.attach_complexity_artifact_to_report(output)
    velocity = next(item for item in output["sections"] if item["id"] == "velocity_complexity")

    assert output["complexity_evidence_provenance"]["status"] == "unavailable"
    assert output["complexity_evidence_provenance"]["fetch_provenance"]["source_paths_fetched"] == 0
    assert any("attempted" in str(line) and "fetched none" in str(line) for line in velocity["unavailable"])
    assert any("API rate limit exceeded" in str(line) for line in velocity["unavailable"])
    assert velocity["score"] == 89


def test_valid_api_profile_replaces_zero_worker_profile_without_approving_delivery() -> None:
    client = _BudgetClient(successful_source_fetches=8)
    profile = compat.fetch_repository_profile_with_budget_provenance(
        client,
        "BoneManTGRM/NICO",
        {"default_branch": "main"},
    )["complexity_profile"]
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "client_ready": False,
        "human_review_required": True,
        "complexity_engine": {
            "source_file_count": 650,
            "analyzed_file_count": 0,
            "total_loc": 0,
            "total_functions": 0,
            "risk_level": "review_required",
        },
    }

    output = compat.attach_api_sample_complexity_with_provenance(result, profile)

    assert output["complexity_engine"]["source"] == "github_api_exact_commit_bounded_sample"
    assert output["complexity_engine"]["analyzed_file_count"] == 8
    assert output["complexity_evidence_provenance"]["status"] == "attached"
    assert output["client_ready"] is False
    assert output["human_review_required"] is True
