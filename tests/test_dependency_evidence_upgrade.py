from pathlib import Path

import nico.hosted_assessment as hosted
from nico.final_report_consistency import finalize_express_result_consistency


def test_dependency_scoring_records_frontend_lockfile(monkeypatch):
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

    assert not any("no JavaScript lockfile" in item for item in result["findings"])
    assert any("Lockfile evidence found" in item for item in result["evidence"])


def test_final_scoring_lifts_clean_dependency_evidence():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": [
                {
                    "id": "dependency_health",
                    "label": "Dependency / Library Ecosystem",
                    "score": 60,
                    "status": "yellow",
                    "summary": "Dependency manifests and lockfile evidence were inspected from repository files.",
                    "evidence": [
                        "requirements.txt found with 2 active dependency lines.",
                        "apps/web/package.json found with 2 npm dependency entries across dependency sections.",
                        "Lockfile evidence found: apps/web/package-lock.json.",
                        "OSV returned no vulnerability records for 8 pinned dependency query/queries.",
                    ],
                    "findings": ["OSV returned no vulnerability records for 8 pinned dependency query/queries."],
                    "unavailable": [],
                }
            ],
            "reports": {},
        }
    )

    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    assert dependency["score"] >= 86
    assert dependency["status"] == "green"
    assert not dependency["findings"]


def test_dependency_policy_files_are_tracked():
    assert Path(".github/dependabot.yml").exists()
    assert Path("docs/dependency-policy.md").exists()
    assert Path("apps/web/package-lock.json").exists()
