from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "web" / "app" / "AssessmentFinalPresentation.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_final_report_presentation_is_mounted_globally() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentFinalPresentation from "./AssessmentFinalPresentation";' in layout
    assert "<AssessmentFinalPresentation />" in layout


def test_workspace_replaces_obsolete_report_and_status_language() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert '"Download draft PDF": "Download final report"' in source
    assert 'replace(/\\bunavailable\\b/gi, "Evidence limited")' in source
    assert 'labelNode.textContent = spanish ? "Persistencia" : "Persistence";' in source
    assert 'value.textContent = spanish ? "Registrado" : "Recorded";' in source
    assert 'value.textContent = spanish ? "Durabilidad verificada" : "Durability verified";' in source


def test_presentation_does_not_relabel_recorded_storage_as_durable() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    recorded_branch = source.split("if (/recorded", 1)[1].split("}", 1)[0]
    assert "Durability verified" not in recorded_branch
    assert "Recorded" in recorded_branch
