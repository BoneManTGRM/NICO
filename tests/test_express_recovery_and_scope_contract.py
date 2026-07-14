from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASYNC_API = ROOT / "nico" / "express_async_api.py"
RECOVERY_COMPAT = ROOT / "nico" / "express_recovery_compat.py"
BLOCK_INSTALLER = ROOT / "nico" / "assessment_block_messages.py"
BRIDGE = ROOT / "apps" / "web" / "app" / "AssessmentApiTransportBridge.tsx"
RECOVERY_PAGE = ROOT / "apps" / "web" / "app" / "operations" / "recovery" / "page.tsx"
RECOVERY_PANEL = ROOT / "apps" / "web" / "app" / "operations" / "AssessmentRecoveryPanel.tsx"


def test_express_status_is_tenant_bound_and_unknown_states_fail_closed() -> None:
    source = ASYNC_API.read_text(encoding="utf-8")

    assert "from hmac import compare_digest" in source
    assert 'stored_customer = str(record.get("customer_id")' in source
    assert 'stored_project = str(record.get("project_id")' in source
    assert 'compare_digest(str(req.customer_id or "default_customer"), stored_customer)' in source
    assert 'compare_digest(' in source
    assert '"Express assessment run not found."' in source
    assert 'code="express_unknown_terminal_state"' in source
    assert 'if status not in _TERMINAL_SUCCESS:' in source


def test_express_start_is_idempotent_per_active_scope_and_capacity_bounded() -> None:
    source = ASYNC_API.read_text(encoding="utf-8")

    assert "MAX_ACTIVE_EXPRESS_RUNS = 2" in source
    assert "_ACTIVE_SCOPE_RUNS" in source
    assert "existing_run_id = _ACTIVE_SCOPE_RUNS.get(key" in source
    assert 'response["duplicate_start_prevented"] = True' in source
    assert 'code": "express_capacity_reached"' in source
    assert '"duplicate_active_scope_start_prevented": True' in source
    assert '"max_active_runs": MAX_ACTIVE_EXPRESS_RUNS' in source


def test_browser_polls_with_the_exact_start_tenant_scope() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    assert "const customerId = boundedText(started.customer_id, 120);" in source
    assert "const projectId = boundedText(started.project_id, 120);" in source
    assert '!runId.startsWith("express_run_") || !customerId || !projectId' in source
    assert '"express_start_missing_identity"' in source
    assert "JSON.stringify({customer_id: customerId, project_id: projectId})" in source
    assert "cross-scope run" in source


def test_express_recovery_is_inventory_only_and_never_automatic() -> None:
    source = RECOVERY_COMPAT.read_text(encoding="utf-8")
    installer = BLOCK_INSTALLER.read_text(encoding="utf-8")

    assert 'recovery.SUPPORTED_WORKFLOWS.add("express")' in source
    assert 'recovery.ACTIVE_ASSESSMENT_STATUSES.add("queued")' in source
    assert 'str(record.get("status") or "") == "interrupted"' in source
    assert '"express_recovery_required"' in source
    assert 'return False, "express_manual_review_required"' in source
    assert '"resume_allowed": False' in source
    assert '"automatic_resume": False' in source
    assert '"same_id_resume": False' in source
    assert "install_express_recovery_compatibility()" in installer


def test_recovery_ui_exposes_express_without_enabling_resume() -> None:
    page = RECOVERY_PAGE.read_text(encoding="utf-8")
    panel = RECOVERY_PANEL.read_text(encoding="utf-8")

    assert "Review interrupted Express, Mid, Full, and scanner work." in page
    assert "Interrupted Express, Mid, and Full runs" in panel
    assert "express_recovery_required?: number" in panel
    assert "Interrupted Express runs are retained for manual review" in panel
    assert 'item.recovery?.resume_allowed ? "Resume same run ID" : "Manual review required"' in panel
    assert "No interrupted Express, Mid, or Full runs require recovery." in panel
