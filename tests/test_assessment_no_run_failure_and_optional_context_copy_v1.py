from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"
EVIDENCE = ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"


def test_no_run_failure_does_not_render_second_terminal_state_panel() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "const preflightIssue = issue && !issue.runCreated ? issue : null;" in source
    assert "const runIssue = issue && issue.runCreated ? issue : null;" in source
    assert "const showStatePanel = Boolean(result?.run_id)" in source
    assert "|| Boolean(runIssue)" in source
    assert '|| phase === "starting";' in source
    assert '["starting", "running", "review_required", "complete", "failed", "timed_out"].includes(phase)' not in source
    assert 'data-assessment-no-run-issue="true"' in source


def test_public_mobile_context_is_truthfully_optional_in_both_locales() -> None:
    source = EVIDENCE.read_text(encoding="utf-8")

    assert 'mobileContextLabel: "Optional client context"' in source
    assert "Client and project names above are optional display metadata" in source
    assert "do not make the fields below required" in source
    assert "Missing values remain unassessed and are never inferred or fabricated" in source

    assert 'mobileContextLabel: "Contexto opcional del cliente"' in source
    assert "Los nombres de cliente y proyecto de arriba son metadatos de presentación opcionales" in source
    assert "no hacen obligatorios los campos de abajo" in source
    assert "nunca se infieren ni se inventan" in source

    assert "When client/project identity is supplied" not in source
    assert "Cuando se proporciona identidad de cliente/proyecto" not in source
    assert "Required only for actual client work" not in source
    assert "Requerido únicamente para trabajo real de cliente" not in source
