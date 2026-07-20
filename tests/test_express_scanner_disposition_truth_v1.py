from nico.express_scanner_disposition_truth_v1 import reconcile_express_scanner_dispositions


def _section(section_id, summary, evidence=None, findings=None, unavailable=None):
    return {
        "id": section_id,
        "label": section_id,
        "summary": summary,
        "status": "yellow",
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def test_dependency_scope_conflict_keeps_exact_snapshot_candidate() -> None:
    result = {
        "sections": [
            _section(
                "dependency_health",
                "Dependency review is verified by clean artifacts.",
                evidence=[
                    "OSV returned no vulnerability records for 12 pinned dependency queries.",
                    "Exact-snapshot osv-scanner status=completed; findings=1; commit=abc123.",
                    "Exact-snapshot pip-audit status=completed; findings=0; commit=abc123.",
                ],
                findings=["osv-scanner returned 1 finding(s) requiring human triage."],
            )
        ]
    }

    reconcile_express_scanner_dispositions(result)
    section = result["sections"][0]

    assert section["scanner_dispositions"]["osv-scanner"]["status"] == "completed_findings"
    assert section["scanner_dispositions"]["pip-audit"]["status"] == "completed_clean"
    assert any("exact-snapshot OSV repository scan returned candidate records" in item for item in section["evidence"])
    assert section["findings"] == ["osv-scanner returned 1 finding(s) requiring human triage."]
    assert "review-limited" in section["summary"]


def test_failed_timeout_and_unavailable_tools_never_become_clean() -> None:
    result = {
        "sections": [
            _section(
                "static_analysis",
                "Static analysis is verified by current-run Bandit, Semgrep, ESLint, and TypeScript artifacts.",
                evidence=[
                    "Exact-snapshot semgrep status=completed; findings=64; commit=abc123.",
                    "Bandit triage artifact attached: blocking=0, needs_review=14.",
                    "Static review finding reconciliation: clean Bandit triage supersedes raw Bandit finding count for release-readiness gating.",
                ],
                findings=["bandit ended with status failed; its output requires human review."],
                unavailable=["eslint was unavailable: No ESLint configuration exists."],
            ),
            _section(
                "secrets_review",
                "Secrets review.",
                evidence=["Exact-snapshot trufflehog status=completed; findings=1; commit=abc123."],
                findings=[
                    "Scanner-worker secret tools reported 27 finding(s).",
                    "gitleaks ended with status timeout.",
                ],
            ),
        ]
    }

    reconcile_express_scanner_dispositions(result)
    static = result["sections"][0]
    secrets = result["sections"][1]

    assert static["scanner_dispositions"]["bandit"]["status"] == "failed"
    assert static["scanner_dispositions"]["eslint"]["status"] == "unavailable"
    assert static["scanner_dispositions"]["semgrep"]["status"] == "completed_findings"
    assert "remain explicitly separated from completed evidence" in static["summary"]
    assert any("failed Bandit execution prevents a clean Bandit conclusion" in item for item in static["evidence"])

    assert secrets["scanner_dispositions"]["gitleaks"]["status"] == "timeout"
    assert secrets["scanner_dispositions"]["trufflehog"]["status"] == "completed_findings"
    assert any("raw candidate(s)" in item for item in secrets["findings"])
    assert "does not establish credential exposure" in secrets["summary"]


def test_global_contract_exposes_one_disposition_per_tool() -> None:
    result = {
        "sections": [
            _section(
                "scanner_worker_evidence",
                "Supplemental scanner evidence.",
                evidence=[
                    "Scanner worker result: pip-audit status=completed; findings=0.",
                    "Scanner worker result: gitleaks status=timeout; findings=1.",
                ],
            )
        ]
    }

    reconcile_express_scanner_dispositions(result)

    assert result["scanner_dispositions"]["pip-audit"]["status"] == "completed_clean"
    assert result["scanner_dispositions"]["gitleaks"]["status"] == "timeout"
    contract = result["express_scanner_disposition_truth"]
    assert contract["one_canonical_disposition_per_tool"] is True
    assert contract["failed_or_timed_out_not_clean"] is True
    assert contract["client_delivery_allowed"] is False
