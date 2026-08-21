from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps" / "web" / "app" / "AssessmentApiTransportBridge.tsx"
RESPONSE = ROOT / "apps" / "web" / "app" / "AssessmentFailureResponseBridge.tsx"
PANEL = ROOT / "apps" / "web" / "app" / "AssessmentFailureEvidencePanel.tsx"


def test_transport_retains_only_bounded_worker_diagnostics() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    for field in (
        "worker_model",
        "worker_exit_code",
        "worker_exit_signal",
        "worker_error_type",
        "worker_error",
        "worker_failure_class",
        "worker_bootstrap",
    ):
        assert field in source

    assert "export function boundedWorkerFailure" in source
    assert 'pick(["worker_error", "error"], 1200)' in source
    assert "worker?: AssessmentWorkerFailureEvidence | null" in source
    assert "worker_traceback" not in source


def test_terminal_bridge_uses_stage_reason_as_code_and_projects_child_error() -> None:
    source = RESPONSE.read_text(encoding="utf-8")

    assert "code: text(stage.error_code, stage.failure_code, stage.code, stage.reason)" in source
    assert "worker: boundedWorkerFailure(stage, stage.stage_execution)" in source
    assert "failedStageResult?.code" in source
    assert "worker?.error" in source
    assert "technical_reason: technicalReason" in source
    assert "worker_failure: worker" in source
    assert "message: technicalReason" in source
    assert "client_delivery_allowed: false" in source


def test_failure_panel_shows_worker_exit_and_removes_duplicate_stage_card() -> None:
    source = PANEL.read_text(encoding="utf-8")

    for label in (
        "Código de salida del proceso",
        "Señal de salida",
        "Tipo de error del proceso",
        "Clase de fallo",
        "Arranque del renderizador",
        "Worker exit code",
        "Worker error type",
        "Renderer bootstrap",
    ):
        assert label in source

    assert "duplicatesPrimaryDiagnostic" in source
    assert "stageRows.map" in source
    assert "failure.progress.map" not in source
    assert "worker_traceback" not in source
