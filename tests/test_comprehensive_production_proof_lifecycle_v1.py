from __future__ import annotations

from pathlib import Path

import pytest

from nico.comprehensive_production_proof_lifecycle_v1 import (
    PROOF_CUSTOMER_ID,
    PROOF_PROJECT_ID,
    cancel_production_proof_record,
)
from nico.comprehensive_run_record import create_comprehensive_run_record


class _Store:
    def __init__(self) -> None:
        self.value = None

    def save(self, record, *, expected_revision: int):
        assert int(record["revision"]) == expected_revision + 1
        self.value = record
        return record

    def load(self, run_id: str):
        assert self.value is not None
        assert self.value["identity"]["run_id"] == run_id
        return self.value


def _record(*, customer_id: str = PROOF_CUSTOMER_ID):
    return create_comprehensive_run_record(
        run_id="comprun_proof_lifecycle",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_proof_lifecycle",
        customer_id=customer_id,
        project_id=PROOF_PROJECT_ID,
        authorized=True,
        assessment_depth="strategic",
        report_language="es-MX",
    )


def test_reserved_proof_can_be_terminalized_without_client_delivery() -> None:
    cancelled = cancel_production_proof_record(
        _Store(),
        _record(),
        reason="production_proof_cancelled",
    )
    assert cancelled["terminal"] is True
    assert cancelled["status"] == "blocked"
    assert cancelled["human_review_required"] is True
    assert cancelled["client_delivery_allowed"] is False
    stage = cancelled["current_stage"]
    assert cancelled["stage_results"][stage]["reason"] == "production_proof_cancelled"


def test_proof_cancel_rejects_normal_client_scope() -> None:
    with pytest.raises(ValueError, match="production_proof_scope_required"):
        cancel_production_proof_record(
            _Store(),
            _record(customer_id="real_customer"),
            reason="production_proof_cancelled",
        )


def test_spanish_proof_is_latest_release_only_and_reserved() -> None:
    workflow = Path(".github/workflows/spanish-comprehensive-production-proof.yml").read_text(
        encoding="utf-8"
    )
    script = Path("scripts/spanish_comprehensive_live_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    assert "group: nico-spanish-comprehensive-production" in workflow
    assert "cancel-in-progress: true" in workflow
    assert 'payload["production_proof_scope_verified"] is True' in workflow
    assert 'PROOF_CUSTOMER_ID = "nico_production_proof"' in script
    assert 'PROOF_PROJECT_ID = "spanish_comprehensive_production"' in script
    assert "production-proof-cancel" in script
    assert "signal.SIGTERM" in script


def test_release_and_green_gates_require_spanish_production_proof() -> None:
    release = Path(".github/workflows/production-release-gate.yml").read_text(
        encoding="utf-8"
    )
    wrapper = Path("scripts/check_production_release_with_spanish.py").read_text(
        encoding="utf-8"
    )
    watch = Path(".github/workflows/production-acceptance-green-watch.yml").read_text(
        encoding="utf-8"
    )
    notifier = Path(
        ".github/workflows/production-acceptance-green-notifier.yml"
    ).read_text(encoding="utf-8")
    assert "check_production_release_with_spanish.py" in release
    assert 'SPANISH_PROOF_WORKFLOW = "Spanish Comprehensive Production Proof"' in wrapper
    required_context = "NICO Spanish Comprehensive Production Proof"
    assert required_context in watch
    assert required_context in notifier

    # The old green watch pointed at an already-completed issue and the old notifier
    # suppressed every future release after its first historical notification. Both
    # monitors must instead be exact-main aware for the Spanish proof to be meaningful.
    assert "statuses: write" in watch
    assert "NICO Production Acceptance Green Watch" in watch
    assert "TRACKING_ISSUE_NUMBER" not in watch
    assert "NOTIFICATION_MARKER_PREFIX" in notifier
    assert "nico-production-acceptance-green-notifier:v2:" in notifier
    assert "notification_marker = f" in notifier
    assert "main_sha" in notifier


def test_spanish_bootstrap_installs_proof_lifecycle_after_full_process_hardening() -> None:
    # Keep this as an explicit exact-head regression: proof cleanup must inherit every
    # physical worker-lifetime guard merged in PR #1253 before it is allowed to cancel.
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_final_report_process_isolation_v1" in source
    assert "install_comprehensive_final_report_process_isolation_hardening_v2" in source
    assert "install_comprehensive_production_proof_lifecycle_v1" in source
    assert source.index("FINAL_REPORT_PROCESS_ISOLATION =") < source.index(
        "FINAL_REPORT_PROCESS_ISOLATION_HARDENING ="
    )
    assert source.index("FINAL_REPORT_PROCESS_ISOLATION_HARDENING =") < source.index(
        "PRODUCTION_PROOF_LIFECYCLE ="
    )
    assert "failed_termination_keeps_renderer_capacity_reserved" in source
    assert "prior_proof_reaper_bound" in source
    assert "proof_cancel_route_bound" in source
    assert "client_run_scope_untouched" in source
