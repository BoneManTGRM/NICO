from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ROOT / "apps/web/app/assessment/assessmentRunRequests.ts"


def test_provider_intake_failures_have_safe_spanish_presentation_messages() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    required_codes = (
        "authorized_nico_operator_required",
        "provider_credential_reference_missing",
        "provider_operationally_disabled",
        "provider_rollout_control_unavailable",
        "repository_snapshot_unavailable",
        "raw_provider_credentials_prohibited",
        "explicit_authorization_required",
        "provider_repository_selection_mismatch",
    )
    for code in required_codes:
        assert f'"{code}"' in source

    required_spanish = (
        "Ingresa un token de operador NICO válido para usar GitLab, Bitbucket o Azure DevOps.",
        "NICO no tiene configurada una credencial del servidor para este proveedor.",
        "El proveedor seleccionado está deshabilitado en la configuración operativa de NICO.",
        "El control operativo de proveedores de NICO no está disponible en este momento.",
        "NICO no pudo capturar la revisión inmutable del repositorio seleccionado.",
        "Las credenciales del proveedor deben permanecer en el servidor.",
        "La URL o el identificador del repositorio no coincide con el proveedor seleccionado.",
    )
    for message in required_spanish:
        assert message in source


def test_unknown_backend_prose_cannot_leak_into_spanish_pre_run_ui() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert 'function spanishCopy(copy: ReturnType<typeof copyFor>): boolean' in source
    assert 'copy === copyFor("es-MX")' in source
    assert "Do not leak arbitrary English backend prose into es-MX presentation" in source
    assert "? copy.runCreationFailureMessage" in source
    assert ": apiError?.message || copy.runCreationFailureMessage" in source


def test_provider_configuration_blocks_are_not_misrepresented_as_started_runs() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "PROVIDER_CONFIGURATION_BLOCK_CODES.has(code)" in source
    assert 'kind: "configuration_blocked"' in source
    assert "message: preRunIssueMessage(apiError, code, copy)" in source
    assert "runCreated," in source
