from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/production-proof-reconciliation.yml")


def test_reconciliation_runs_only_after_successful_main_prerequisite_workflows() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_run:" in text
    assert "Mobile Restart Production Proof" in text
    assert "iOS WebKit Paint Proof" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
    assert "RELEASE_SHA: ${{ github.event.workflow_run.head_sha }}" in text
    assert "cancel-in-progress: false" in text


def test_reconciliation_has_bounded_actions_write_scope_and_exact_sha_selection() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "actions: write" in text
    assert "contents: read" in text
    assert "statuses: read" in text
    assert "SOURCE_CONSUMER_RUN_ID: ${{ github.event.workflow_run.id }}" in text
    assert "SOURCE_CONSUMER_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}" in text
    assert 'str(trigger_run.get("head_sha") or "") != sha' in text
    assert 'str(trigger_run.get("event") or "") != "workflow_run"' in text
    assert 'str(trigger_run.get("run_attempt") or "") != source_consumer_run_attempt' in text
    assert 'marker_match = re.match(r"^(source:\\d+:\\d+) ", description)' in text
    assert "source_bound_status(statuses, context, source_marker)" in text
    assert "rerun-failed-jobs" in text
    assert 'status != "completed"' in text
    assert 'conclusion not in {"failure", "cancelled", "timed_out", "action_required", "stale"}' in text


def test_reconciliation_repairs_only_the_known_dependency_chain() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'mobile_context = "NICO Mobile Restart Production Proof"' in text
    assert 'ios_context = "NICO iOS WebKit Paint Proof"' in text
    assert 'acceptance_context = "NICO Two-Service Production Acceptance"' in text
    assert '"ios-webkit-paint-proof.yml"' in text
    assert '"two-service-production-acceptance.yml"' in text
    assert 'observed[mobile_context] == "success" and observed[ios_context] in {"failure", "error"}' in text
    assert 'observed[ios_context] == "success"' in text
    assert 'observed[acceptance_context] in {"failure", "error"}' in text
    assert "status_item=bound[ios_context]" in text
    assert "status_item=bound[acceptance_context]" in text


def test_reconciliation_never_creates_a_new_assessment_or_replays_successful_jobs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "/rerun-failed-jobs" in text
    assert "/dispatches" not in text
    assert "/comprehensive-run" not in text
    assert "/assessment/" not in text
    assert "client_delivery_allowed" not in text
    assert "human_review_required" not in text
