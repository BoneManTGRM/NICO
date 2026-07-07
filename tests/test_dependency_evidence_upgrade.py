from pathlib import Path

import nico.hosted_assessment as hosted


def test_dependency_scoring_counts_frontend_lockfile(monkeypatch):
    def fake_osv(_dependencies):
        return ["OSV returned no vulnerability records for 8 pinned dependency query/queries."], []

    monkeypatch.setattr(hosted, "query_osv", fake_osv)

    result = hosted.analyze_dependencies(
        {
            "requirements.txt": "fastapi==0.115.6\nrequests==2.32.3\n",
            "apps/web/package.json": '{"dependencies":{"next":"16.2.10","react":"18.3.1"}}',
            "apps/web/package-lock.json": '{"lockfileVersion":3,"requires":true,"packages":{"":{"dependencies":{"next":"16.2.10","react":"18.3.1"}}}}',
        }
    )

    assert result["score"] >= 80
    assert not any("no JavaScript lockfile" in item for item in result["findings"])
    assert any("Lockfile evidence found" in item for item in result["evidence"])


def test_dependency_policy_files_are_tracked():
    assert Path(".github/dependabot.yml").exists()
    assert Path("docs/dependency-policy.md").exists()
    assert Path("apps/web/package-lock.json").exists()
