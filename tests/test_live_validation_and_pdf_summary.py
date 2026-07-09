from nico.hosted_full_evidence_runtime_v2 import ensure_hosted_runtime_evidence
from nico.report_pdf_display_patch import apply_pdf_display_patch


def _section(section_id, label):
    return {"id": section_id, "label": label, "status": "yellow", "score": 74, "summary": "Review limited.", "evidence": [], "findings": [], "unavailable": []}


def _result(refresh=True):
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "authorized_by": "frontend-refresh-full-evidence" if refresh else "standard-express",
        "refresh_full_evidence_requested": refresh,
        "sections": [
            _section("trust_client_readiness", "Trust & Client Readiness"),
            _section("dependency_health", "Dependency / Library Ecosystem"),
            _section("secrets_review", "Secrets Exposure Review"),
            _section("static_analysis", "Static Analysis"),
        ],
    }


def _unavailable_artifact():
    return {
        "worker_execution_state": "completed",
        "tools": {
            "pip-audit": {"tool": "pip-audit", "category": "dependency", "status": "completed", "findings": []},
            "npm-audit": {"tool": "npm-audit", "category": "dependency", "status": "unavailable", "findings": []},
            "osv-scanner": {"tool": "osv-scanner", "category": "dependency", "status": "unavailable", "findings": []},
            "bandit": {"tool": "bandit", "category": "static", "status": "completed", "findings": []},
            "semgrep": {"tool": "semgrep", "category": "static", "status": "unavailable", "findings": []},
            "eslint": {"tool": "eslint", "category": "static", "status": "unavailable", "findings": []},
            "typescript": {"tool": "typescript", "category": "static", "status": "unavailable", "findings": []},
            "gitleaks": {"tool": "gitleaks", "category": "secret", "status": "completed", "findings": [], "scans_git_history": True},
            "trufflehog": {"tool": "trufflehog", "category": "secret", "status": "unavailable", "findings": [], "scans_git_history": True},
        },
    }


def test_refresh_validation_status_is_visible_when_tools_remain_missing(monkeypatch):
    monkeypatch.setattr("nico.hosted_full_evidence_runtime_v2.run_hosted_scanner_worker", lambda payload: _unavailable_artifact())

    result = ensure_hosted_runtime_evidence(_result(refresh=True))
    sections = {section["id"]: section for section in result["sections"]}

    trust_text = "\n".join(sections["trust_client_readiness"]["evidence"])
    dependency_text = "\n".join(sections["dependency_health"]["unavailable"])
    static_text = "\n".join(sections["static_analysis"]["unavailable"])
    secret_text = "\n".join(sections["secrets_review"]["unavailable"])

    assert "Refresh Full Evidence runtime validation" in trust_text
    assert "npm-audit" in dependency_text
    assert "semgrep" in static_text
    assert "trufflehog" in secret_text
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["refresh_full_evidence_requested"] is True


def test_standard_express_does_not_surface_refresh_validation(monkeypatch):
    calls = []
    monkeypatch.setattr("nico.hosted_full_evidence_runtime_v2.run_hosted_scanner_worker", lambda payload: calls.append(payload) or _unavailable_artifact())

    result = ensure_hosted_runtime_evidence(_result(refresh=False))
    sections = {section["id"]: section for section in result["sections"]}

    assert calls == []
    assert sections["trust_client_readiness"]["evidence"] == []
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["status"] == "skipped_no_explicit_refresh_request"


def test_pdf_summary_clean_text_does_not_truncate_long_summary():
    from nico import assessment_quality

    apply_pdf_display_patch()
    long_summary = "Executive summary sentence. " * 120

    assert "[truncated]" not in assessment_quality._clean_text(long_summary, 900)
    assert assessment_quality._clean_text(long_summary, 120).endswith("... [truncated]")
