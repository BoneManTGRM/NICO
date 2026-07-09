from nico.hosted_assessment import analyze_ci
from nico.hosted_full_evidence_runtime_v2 import ensure_hosted_runtime_evidence
from nico.hosted_report_regression_patch import _prepare_refresh_payload
from nico.trust_report_display import attach_trust_report_display


def _section(section_id, label):
    return {"id": section_id, "label": label, "status": "yellow", "score": 74, "summary": "Review limited.", "evidence": [], "findings": [], "unavailable": []}


def _result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "authorized_by": "frontend-refresh-full-evidence",
        "refresh_full_evidence_requested": True,
        "maturity_signal": {"level": "Mid", "score": 79},
        "sections": [
            _section("dependency_health", "Dependency / Library Ecosystem"),
            _section("secrets_review", "Secrets Exposure Review"),
            _section("static_analysis", "Static Analysis"),
        ],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def _mixed_artifact():
    def tool(name, category, status="completed", reason=""):
        payload = {"tool": name, "category": category, "status": status, "returncode": 0 if status == "completed" else None, "findings": [], "verified_for_this_report": status == "completed"}
        if reason:
            payload["reason"] = reason
        return payload

    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "completed",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T16:20:00Z",
        "tools": {
            "pip-audit": tool("pip-audit", "dependency"),
            "npm-audit": tool("npm-audit", "dependency", "unavailable", "npm executable unavailable"),
            "osv-scanner": tool("osv-scanner", "dependency", "unavailable", "osv-scanner binary unavailable and fallback failed"),
            "bandit": tool("bandit", "static"),
            "semgrep": tool("semgrep", "static", "unavailable", "semgrep not installed"),
            "eslint": tool("eslint", "static", "unavailable", "project commands disabled"),
            "typescript": tool("typescript", "static", "unavailable", "project commands disabled"),
            "gitleaks": tool("gitleaks", "secret"),
            "trufflehog": tool("trufflehog", "secret", "unavailable", "trufflehog not installed"),
        },
    }


def test_authorized_frontend_payload_requests_full_evidence_by_default():
    payload = _prepare_refresh_payload({"repository": "BoneManTGRM/NICO", "authorized": True, "authorized_by": "unspecified"})

    assert payload["refresh_full_evidence_requested"] is True
    assert payload["authorized_by"] == "frontend-refresh-full-evidence"
    assert payload["run_scanner_worker"] is True
    assert payload["scanner_worker_autorun"] is True
    assert payload["full_history_secret_scan"] is True


def test_runtime_validation_exposes_truthful_tool_records(monkeypatch):
    monkeypatch.setattr("nico.hosted_full_evidence_runtime_v2.run_hosted_scanner_worker", lambda payload: _mixed_artifact())

    result = ensure_hosted_runtime_evidence(_result())
    validation = result["hosted_full_evidence_runtime_validation"]
    records = {item["tool"]: item for item in validation["tool_records"]}

    assert validation["status"] == "completed"
    assert records["pip-audit"]["verified_for_this_report"] is True
    assert records["npm-audit"]["status"] == "unavailable"
    assert "npm executable unavailable" in records["npm-audit"]["reason"]
    assert "trufflehog" in validation["missing_or_unavailable_tools"]
    assert any("npm-audit current-run status=unavailable" in item for item in result["sections"][0]["unavailable"])


def test_trust_display_surfaces_runtime_validation(monkeypatch):
    monkeypatch.setattr("nico.hosted_full_evidence_runtime_v2.run_hosted_scanner_worker", lambda payload: _mixed_artifact())

    result = ensure_hosted_runtime_evidence(_result())
    result = attach_trust_report_display(result)
    trust = next(section for section in result["sections"] if section["id"] == "trust_readiness")
    evidence_text = "\n".join(trust["evidence"])

    assert "Refresh Full Evidence runtime validation" in evidence_text
    assert "npm-audit=unavailable" in evidence_text


def test_current_green_ci_is_scored_separately_from_historical_failures():
    workflows = {
        ".github/workflows/nico-ci.yml": "permissions:\n  contents: read\nsteps:\n  - run: pytest\n  - run: npm run lint\n  - run: docker build .",
        ".github/workflows/node.js.yml": "permissions:\n  contents: read\nsteps:\n  - run: npm run lint\n  - run: next build",
    }
    current = [
        {"name": "NICO CI", "conclusion": "success"},
        {"name": "Node.js CI", "conclusion": "success"},
        {"name": "CodeQL Advanced", "conclusion": "success"},
        {"name": "Audit Evidence", "conclusion": "success"},
        {"name": "Security Audit Evidence", "conclusion": "success"},
    ]
    history = [{"name": "NICO CI", "conclusion": "failure"} for _ in range(29)] + [{"name": "NICO CI", "conclusion": "success"} for _ in range(66)]

    result = analyze_ci(workflows, [], current + history, None)
    evidence = "\n".join(result["evidence"])

    assert result["score"] >= 88
    assert "Current release-readiness latest checks" in evidence
    assert "Historical workflow reliability includes 29 non-success" in evidence
