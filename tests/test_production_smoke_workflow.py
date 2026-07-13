from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nico.production_assessment_smoke import (
    CONFIRMATION_PHRASE,
    SmokeConfig,
    SmokeFailure,
    failed_artifact,
    validate_config,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-smoke.yml"
BROWSER_SCRIPT = ROOT / "scripts" / "check_production_assessment_page.mjs"
SHA = "a" * 40


def config(**overrides: Any) -> SmokeConfig:
    values: dict[str, Any] = {
        "frontend_url": "https://app.nicoaudit.com",
        "backend_url": "https://nico-production-690a.up.railway.app",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_nico_smoke",
        "project_id": "project_nico_smoke",
        "authorization_reference": "authorization/ref-1",
        "github_repository": "BoneManTGRM/NICO",
        "github_sha": SHA,
        "confirmation": CONFIRMATION_PHRASE,
        "poll_attempts": 3,
        "poll_interval_seconds": 0,
    }
    values.update(overrides)
    return SmokeConfig(**values)

def test_authorization_reference_rejects_credential_like_values() -> None:
    environment = {
        "NICO_PRODUCTION_SMOKE_ALLOWLIST": "bonemantgrm/nico",
        "NICO_PRODUCTION_SMOKE_FRONTEND_HOSTS": "app.nicoaudit.com",
        "NICO_PRODUCTION_SMOKE_BACKEND_HOSTS": "nico-production-690a.up.railway.app",
        "NICO_PRODUCTION_SMOKE_ADMIN_TOKEN": "configured-secret",
        "GITHUB_TOKEN": "configured-github-token",
    }
    with pytest.raises(SmokeFailure) as error:
        validate_config(config(authorization_reference="token/actual-secret"), environment)
    assert error.value.code == "unsafe_authorization_reference"


def test_failed_artifact_does_not_retain_unvalidated_scope_values() -> None:
    unsafe = config(repository="https://github.com/BoneManTGRM/NICO?token=secret", customer_id="secret value")
    artifact = failed_artifact(unsafe, "blocked", "safe message")
    assert artifact["repository"] == ""
    assert artifact["customer_id"] == ""
    assert artifact["live_claim"] is False
    assert artifact["authorization_confirmed"] is False
    assert "secret" not in json.dumps(artifact)


def test_manual_workflow_uses_environment_secret_and_protected_inputs() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    trigger = source.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert "pull_request:" not in trigger
    assert "push:" not in trigger
    assert "environment: production-smoke" in source
    assert "cancel-in-progress: false" in source
    assert "persist-credentials: false" in source
    assert "NICO_PRODUCTION_SMOKE_ADMIN_TOKEN: ${{ secrets.NICO_PRODUCTION_SMOKE_ADMIN_TOKEN }}" in source
    assert "--repository \"$INPUT_REPOSITORY\"" in source
    assert "--repository \"${{ inputs.repository }}\"" not in source
    assert "if: always()" in source

    inputs = trigger.split("permissions:", 1)[0]
    assert "admin_token:" not in inputs
    assert "NICO_PRODUCTION_SMOKE_ADMIN_TOKEN" not in inputs


def test_browser_check_never_clicks_a_run_button() -> None:
    source = BROWSER_SCRIPT.read_text(encoding="utf-8")
    assert "no_assessment_started: true" in source
    assert 'request.method() === "POST"' in source
    assert "assessmentPosts.length === 0" in source
    assert "expressRun.click" not in source
    assert 'getByRole("button", {name: "Run Express assessment"}).click' not in source
