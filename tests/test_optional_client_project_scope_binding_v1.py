from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "apps/web/app/assessment/assessmentStatus.ts"
RUN = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_optional_client_and_project_labels_do_not_mint_tenant_scope_ids() -> None:
    status = _text(STATUS)
    scope = status.split("export function scopeId", 1)[1].split("export function toneKey", 1)[0]

    assert 'prefix === "customer" && fallback === "default_customer"' in scope
    assert 'prefix === "project" && fallback === "default_project"' in scope
    assert "return fallback;" in scope
    assert "const slug = value" in scope


def test_optional_names_remain_report_metadata_while_scope_stays_canonical() -> None:
    run = _text(RUN)

    assert 'customerId: scopeId("customer", client, "default_customer")' in run
    assert 'projectId: scopeId("project", project, "default_project")' in run
    assert "customer_id: scope.customerId" in run
    assert "project_id: scope.projectId" in run
    assert "client_name: client" in run
    assert "project_name: project" in run


def test_scope_guard_is_narrow_and_does_not_disable_generic_scope_slugging() -> None:
    status = _text(STATUS)
    scope = status.split("export function scopeId", 1)[1].split("export function toneKey", 1)[0]

    assert 'return slug ? `${prefix}_${slug}` : fallback;' in scope
    assert 'prefix === "customer"' in scope
    assert 'prefix === "project"' in scope
