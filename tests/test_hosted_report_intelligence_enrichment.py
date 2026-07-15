from __future__ import annotations

import re

from nico.hosted_report_intelligence_enrichment import (
    enrich_hosted_result,
    structured_source_findings,
)


class FakeClient:
    def get_repo(self, repo: str):
        return {"default_branch": "main", "name": repo.split("/")[-1]}, None

    def get_text_file(self, repo: str, path: str):
        return None, "not needed"


class FakeHosted:
    RISK_PATTERNS = [
        (
            "python_shell_true",
            re.compile(r"shell\s*=\s*True"),
            "subprocess shell=True expands command-injection risk.",
        )
    ]
    SECRET_PATTERNS = [
        ("github_token", re.compile(r"ghp_[A-Za-z0-9]{20,}"))
    ]
    GitHubAssessmentClient = FakeClient

    @staticmethod
    def mask_secret(value: str) -> str:
        return value[:4] + "..." + value[-4:]

    @staticmethod
    def fetch_repository_profile(client, repo, repo_meta):
        return {
            "root_items": ["nico", "apps", "docs"],
            "tree_paths": [
                "nico/__init__.py",
                "nico/worker.py",
                "apps/web/app/dashboard/page.tsx",
                "docs/PROJECT_STATUS.md",
            ],
            "files": {
                "nico/__init__.py": "install_one()\ninstall_two()\n",
                "nico/worker.py": "subprocess.run(command, shell=True)\n",
                "apps/web/app/dashboard/page.tsx": "export {default} from '../page';\n",
                "docs/PROJECT_STATUS.md": "Current status.\n",
            },
            "unavailable": [],
        }

    @staticmethod
    def build_markdown(result):
        return (
            "# Report\n\n"
            "## Repository Quality and Governance Signals\n\n"
            f"Findings: {result.get('repository_quality_signals', {}).get('finding_count', 0)}\n\n"
            "## Prioritized Repair Intelligence\n"
        )

    @staticmethod
    def build_html(markdown: str) -> str:
        return f"<html><body><pre>{markdown}</pre></body></html>"

    @staticmethod
    def build_pdf_base64(markdown: str):
        return None, "PDF unavailable in unit fixture."


def test_structured_source_findings_produce_report_only_security_candidate() -> None:
    findings = structured_source_findings(
        FakeHosted,
        {"nico/worker.py": "subprocess.run(command, shell=True)\n"},
    )

    assert len(findings) == 1
    assert findings[0]["category"] == "python_shell_true"
    assert findings[0]["severity"] == "high"
    assert findings[0]["affected_files"] == ["nico/worker.py"]
    assert "shell=True" in findings[0]["evidence"][1]
    assert findings[0]["source_context"] == "production_or_configuration"


def test_secret_source_finding_masks_raw_value() -> None:
    token = "gh" + "p_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    findings = structured_source_findings(
        FakeHosted,
        {"settings.py": f"TOKEN = '{token}'\n"},
    )

    secret = next(item for item in findings if item["category"] == "secret_exposure")
    rendered = " ".join(secret["evidence"])
    assert token not in rendered
    assert "ghp_...WXYZ" in rendered


def test_nonproduction_source_patterns_are_not_prioritized() -> None:
    findings = structured_source_findings(
        FakeHosted,
        {
            "tests/test_worker.py": "subprocess.run(command, shell=True)\n",
            "docs/example.py": "subprocess.run(command, shell=True)\n",
        },
    )

    assert findings == []


def test_enrichment_attaches_quality_repair_intelligence_and_exports(monkeypatch) -> None:
    monkeypatch.setattr(
        "nico.hosted_report_intelligence_enrichment.get_default_branch_head",
        lambda client, repo, branch: ("a" * 40, None),
    )
    monkeypatch.setattr(
        "nico.hosted_report_intelligence_enrichment.get_paginated_branches",
        lambda client, repo: ([{"name": f"branch-{index}"} for index in range(260)], None, False),
    )
    monkeypatch.setattr(
        "nico.hosted_report_intelligence_enrichment.get_security_posture",
        lambda client, repo: {
            "code_scanning": {"status": "available", "open_alert_count": 0},
            "secret_scanning": {"status": "available", "open_alert_count": 0},
            "dependabot": {"status": "disabled", "message": "disabled"},
        },
    )
    result = {
        "status": "complete",
        "repository": "owner/repo",
        "repository_metadata": {},
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 80,
                "status": "green",
                "summary": "Static review.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            }
        ],
        "findings": [],
        "repairs": [],
    }

    enriched = enrich_hosted_result(FakeHosted, result)

    assert enriched["repository_metadata"]["branch_count"] == 260
    assert enriched["repository_quality_signals"]["finding_count"] >= 2
    assert enriched["repair_intelligence"]["candidate_count"] >= 3
    assert enriched["repair_intelligence"]["mode"] == "report_only"
    assert enriched["repair_intelligence"]["policy"]["automatic_application_allowed"] is False
    assert any(
        item["category"] == "python_shell_true"
        for item in enriched["repair_intelligence"]["candidates"]
    )
    frontend = enriched["repository_quality_signals"]["groups"]["frontend_routes"]
    assert frontend["explicit_placeholders"] == []
    assert frontend["route_aliases"] == ["apps/web/app/dashboard/page.tsx"]
    assert "## Prioritized Repair Intelligence" in enriched["reports"]["markdown"]
    assert "## Repository Quality and Governance Signals" in enriched["reports"]["markdown"]
    assert enriched["reports"]["html"].startswith("<html>")
    assert "PDF unavailable in unit fixture." in enriched["unavailable_data_notes"]
