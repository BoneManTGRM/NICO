from nico import client_acceptance_evidence as acceptance_module
from nico.final_report_consistency import finalize_express_result_consistency
from nico.project_trend_evidence import STORE


def _section(section_id, label, score, evidence=None, findings=None):
    return {
        "id": section_id,
        "label": label,
        "status": "green",
        "score": score,
        "summary": f"{label} summary",
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": [],
    }


def _release_ready_result(score=92):
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "generated_at": "2026-07-07T15:00:00Z",
        "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
        "maturity_signal": {"level": "Senior", "score": score},
        "executive_summary": "old",
        "sections": [
            _section("code_audit", "Code Audit", 86, ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2."]),
            _section("dependency_health", "Dependency / Library Ecosystem", 90, ["Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities."]),
            _section(
                "secrets_review",
                "Secrets Exposure Review",
                93,
                [
                    "Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.",
                    "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                ],
            ),
            _section("static_analysis", "Static Analysis", 86, ["Parsed Bandit and Semgrep artifacts reported zero scanner findings."]),
            _section("ci_cd", "CI/CD Analysis", 95, ["Current GitHub Actions scanner artifact sets were fetched and parsed successfully."]),
            _section("architecture_debt", "Architecture & Technical Debt", 94, ["Repository root contains nico/."]),
            _section(
                "velocity_complexity",
                "Velocity / Complexity",
                90,
                [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 54 PRs / 100 commits = 0.54.",
                    "Source-file footprint from recursive tree: 101 files.",
                ],
            ),
        ],
        "reports": {},
    }


def _prior_rows():
    return [
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T10:00:00Z", "maturity_signal": {"score": 90}}},
        {"workflow": "express", "project_id": "default_project", "payload": {"status": "complete", "generated_at": "2026-07-07T12:00:00Z", "maturity_signal": {"score": 91}}},
    ]


def test_approved_acceptance_adds_scored_section_and_lifts_final_score(monkeypatch):
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: _prior_rows() if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})
    monkeypatch.setattr(
        acceptance_module,
        "list_approvals",
        lambda customer_id=None, project_id=None: [
            {
                "approval_id": "approval_final_1",
                "customer_id": "default_customer",
                "project_id": "default_project",
                "requested_action": "final_report_approval",
                "status": "approved",
                "approver": "human_reviewer",
                "evidence": ["reviewed report", "approved final delivery"],
                "updated_at": "2026-07-07T14:30:00Z",
                "audit_log": [{"action": "approved", "actor": "human_reviewer", "note": "Report reviewed and accepted."}],
            }
        ],
    )

    finalized = finalize_express_result_consistency(_release_ready_result())
    acceptance = next(section for section in finalized["sections"] if section["id"] == "client_acceptance")
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert finalized["client_acceptance"]["status"] == "accepted"
    assert acceptance["status"] == "green"
    assert acceptance["score"] == 96
    assert velocity["score"] == 96
    assert finalized["maturity_signal"]["score"] == 92
    assert "Senior (92/100)" in finalized["executive_summary"]


def test_missing_acceptance_is_gray_and_does_not_change_score(monkeypatch):
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: _prior_rows() if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})
    monkeypatch.setattr(acceptance_module, "list_approvals", lambda customer_id=None, project_id=None: [])

    finalized = finalize_express_result_consistency(_release_ready_result())
    acceptance = next(section for section in finalized["sections"] if section["id"] == "client_acceptance")
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert finalized["client_acceptance"]["status"] == "missing"
    assert acceptance["status"] == "gray"
    assert acceptance["score"] == 0
    assert velocity["score"] == 94
    assert finalized["maturity_signal"]["score"] == 91


def test_pending_acceptance_does_not_score(monkeypatch):
    monkeypatch.setattr(STORE, "list", lambda table, **kwargs: _prior_rows() if table == "assessment_runs" else [])
    monkeypatch.setattr(STORE, "status", lambda: {"adapter": "memory"})
    monkeypatch.setattr(
        acceptance_module,
        "list_approvals",
        lambda customer_id=None, project_id=None: [
            {
                "approval_id": "approval_pending_1",
                "customer_id": "default_customer",
                "project_id": "default_project",
                "requested_action": "final_report_approval",
                "status": "pending",
                "evidence": ["awaiting review"],
            }
        ],
    )

    finalized = finalize_express_result_consistency(_release_ready_result())
    acceptance = next(section for section in finalized["sections"] if section["id"] == "client_acceptance")

    assert finalized["client_acceptance"]["status"] == "missing"
    assert finalized["client_acceptance"]["pending_count"] == 1
    assert acceptance["status"] == "gray"
