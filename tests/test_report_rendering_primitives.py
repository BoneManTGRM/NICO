from nico.report_rendering_primitives import (
    normalize_evidence_cards,
    normalize_metrics,
    normalize_repair_actions,
    reportlab_style_tokens,
    validate_rendering_payload,
)


def test_rendering_primitives_normalize_and_deduplicate() -> None:
    metrics = normalize_metrics([
        {"label": "Technical score", "value": 84, "tone": "success"},
        {"label": "Technical score", "value": 10, "tone": "danger"},
        {"label": "Evidence coverage", "value": "93%"},
        {"label": "Confidence", "value": "High"},
        {"label": "Approval", "value": "Human review required", "tone": "warning"},
    ])
    assert len(metrics) == 4
    assert metrics[0].value == "84"
    assert metrics[0].tone == "success"


def test_evidence_cards_preserve_identity_and_acceptance_truth() -> None:
    cards = normalize_evidence_cards([
        {
            "id": "EV-001",
            "source": "GitHub Actions",
            "analyzer": "pytest",
            "snapshot_commit_sha": "abc123",
            "confidence": "high",
            "scoring_acceptance": "accepted",
            "disposition": "verified",
        }
    ])
    assert cards[0].evidence_id == "EV-001"
    assert cards[0].snapshot == "abc123"
    assert cards[0].acceptance == "accepted"


def test_repair_actions_require_verification_and_rollback() -> None:
    actions = normalize_repair_actions([
        {
            "label": "Resolve static-analysis evidence gap",
            "impact": "Limits confidence in code-risk conclusions.",
            "action": "Run analyzers against the immutable snapshot.",
            "owner": "Engineering lead",
            "effort": "2-4 hours",
            "verification": "Retain parseable output and rerun the assessment.",
        }
    ])
    assert actions[0].priority == "P1"
    assert "reversible" in actions[0].rollback.lower()


def test_payload_validation_fails_closed_for_missing_client_truth() -> None:
    metrics = normalize_metrics([
        {"label": "Score", "value": 80},
        {"label": "Coverage", "value": "90%"},
        {"label": "Confidence", "value": "High"},
        {"label": "Approval", "value": "Review required"},
    ])
    cards = normalize_evidence_cards([
        {
            "id": "EV-002",
            "source": "Repository",
            "analyzer": "mapper",
            "confidence": "high",
            "disposition": "retained",
        }
    ])
    issues = validate_rendering_payload(metrics=metrics, evidence_cards=cards, repair_actions=())
    assert "evidence_snapshot_required:EV-002" in issues
    assert "evidence_acceptance_required:EV-002" in issues
    assert "repair_actions_required" in issues


def test_style_tokens_are_derived_from_canonical_design_system() -> None:
    tokens = reportlab_style_tokens()
    assert tokens["version"] == "nico-report-design-v1"
    assert tokens["typography"]["body_pt"] >= 8
    assert tokens["layout"]["table_header_repeat"] is True
    assert "executive_dashboard" in tokens["required_components"]
