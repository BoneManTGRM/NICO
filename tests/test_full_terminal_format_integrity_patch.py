from __future__ import annotations

from nico import full_assessment_idempotent_handlers as handlers
from nico.full_terminal_format_integrity_patch import install_full_terminal_format_integrity


def _context() -> dict:
    return {"run_id": "fullrun_format", "customer_id": "customer", "project_id": "project"}


def _install_with(monkeypatch, package: dict) -> None:
    def fake_handler(_context: dict, _outputs: dict) -> dict:
        return {
            "status": "complete",
            "message": "generated",
            "report_package": package,
            "reports": {},
            "evidence": {"run_id": "fullrun_format"},
        }

    monkeypatch.setattr(handlers, "_reports_handler", fake_handler)
    install_full_terminal_format_integrity()


def test_full_report_fails_closed_when_html_is_missing(monkeypatch) -> None:
    _install_with(monkeypatch, {"formats": {"markdown": "# Full", "html": "", "pdf": "JVBERi0="}, "pdf_error": ""})
    result = handlers._reports_handler(_context(), {})
    assert result["status"] == "limited"
    assert result["format_integrity"]["missing_formats"] == ["html"]
    assert result["evidence"]["format_equivalence_ready"] is False


def test_full_report_requires_pdf_without_pdf_error(monkeypatch) -> None:
    _install_with(monkeypatch, {"formats": {"markdown": "# Full", "html": "<h1>Full</h1>", "pdf": "JVBERi0="}, "pdf_error": "render failed"})
    result = handlers._reports_handler(_context(), {})
    assert result["status"] == "limited"
    assert result["format_integrity"]["missing_formats"] == ["pdf"]


def test_full_report_is_complete_with_all_required_formats(monkeypatch) -> None:
    _install_with(monkeypatch, {"formats": {"markdown": "# Full", "html": "<h1>Full</h1>", "pdf": "JVBERi0="}, "pdf_error": ""})
    result = handlers._reports_handler(_context(), {})
    assert result["status"] == "complete"
    assert result["format_integrity"]["missing_formats"] == []
    assert result["evidence"]["available_formats"] == ["markdown", "html", "pdf"]
    assert result["evidence"]["format_equivalence_ready"] is True
