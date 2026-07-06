from nico.service_workflows import build_mid_assessment, build_retainer_ops


def test_mid_workflow_requires_authorization():
    result = build_mid_assessment({"authorized": False})
    assert result["status"] == "blocked"
    assert "authorization" in result["error"].lower()


def test_mid_workflow_returns_reports_and_readiness():
    result = build_mid_assessment({
        "authorized": True,
        "client_name": "Test Client",
        "project_name": "Test Project",
        "qa_evidence": "Login flow passes on iOS\nCheckout error reproduced with steps",
        "parity_notes": "Android and iOS login copy match",
        "stakeholder_notes": "Primary pain point is release predictability",
        "roadmap_notes": "Month 1 stabilize auth and QA",
        "known_risks": "Payment flow needs regression testing",
    })
    assert result["status"] == "complete"
    assert result["target_coverage"] == "75-85%"
    assert result["human_review_required"] is True
    assert result["evidence_readiness"]["readiness_score"] > 0
    assert "markdown" in result["reports"]
    assert "html" in result["reports"]


def test_retainer_workflow_returns_reports_and_approval_queue():
    result = build_retainer_ops({
        "authorized": True,
        "client_name": "Test Client",
        "project_name": "Test Project",
        "commit_summary": "Three backend assessment commits merged",
        "pr_summary": "One dashboard PR reviewed",
        "issue_summary": "Two QA issues open",
        "blockers": "Waiting on client API access",
        "release_notes": "Staged Railway deploy ready",
        "roadmap_notes": "Next month expands QA evidence intake",
    })
    assert result["status"] == "complete"
    assert result["target_coverage"] == "55-70%"
    assert result["human_review_required"] is True
    assert result["human_approval_queue"]
    assert "markdown" in result["reports"]
    assert "html" in result["reports"]
