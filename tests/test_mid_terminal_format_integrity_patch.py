from __future__ import annotations

import base64
import hashlib

from nico import mid_status_read_path as read_path
from nico.storage import MemoryAdapter


def _record() -> dict:
    return {
        "run_id": "midrun_format_integrity",
        "report_id": "report_format_integrity",
        "customer_id": "customer_format_integrity",
        "project_id": "project_format_integrity",
    }


def _result() -> dict:
    return {
        "status": "complete",
        "mid_report": {"report_id": "report_format_integrity", "status": "complete"},
    }


def _store(*, markdown: str = "# Mid", html: str = "<h1>Mid</h1>", pdf: bytes | None = None) -> MemoryAdapter:
    pdf_bytes = pdf if pdf is not None else b"%PDF-1.4\n%%EOF\n"
    store = MemoryAdapter()
    store.put(
        "reports",
        "report_format_integrity",
        {
            "record_type": "mid_assessment_report",
            "status": "complete",
            "report_id": "report_format_integrity",
            "run_id": "midrun_format_integrity",
            "customer_id": "customer_format_integrity",
            "project_id": "project_format_integrity",
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "formats": {
                "markdown": markdown,
                "html": html,
                "pdf": base64.b64encode(pdf_bytes).decode("ascii"),
            },
            "client_delivery_allowed": False,
        },
    )
    return store


def test_mid_terminal_artifact_requires_html_for_complete_status(monkeypatch) -> None:
    monkeypatch.setattr(read_path, "STORE", _store(html=""))

    output, complete = read_path._rehydrate_final_report(_record(), _result())

    assert complete is False
    assert output["report_artifact_status"]["status"] == "limited"
    assert output["report_artifact_status"]["html_available"] is False
    assert output["report_artifact_status"]["format_equivalence_ready"] is False
    assert output["report_artifact_status"]["missing_formats"] == ["html"]
    assert "html" in output["report_format_error"]


def test_mid_terminal_artifact_requires_all_three_formats(monkeypatch) -> None:
    monkeypatch.setattr(read_path, "STORE", _store())

    output, complete = read_path._rehydrate_final_report(_record(), _result())

    assert complete is True
    assert output["report_artifact_status"]["status"] == "complete"
    assert output["report_artifact_status"]["required_formats"] == ["markdown", "html", "pdf"]
    assert output["report_artifact_status"]["missing_formats"] == []
    assert output["report_artifact_status"]["format_equivalence_ready"] is True
    assert "report_format_error" not in output


def test_mid_terminal_artifact_rejects_non_pdf_bytes_even_when_other_formats_exist(monkeypatch) -> None:
    monkeypatch.setattr(read_path, "STORE", _store(pdf=b"not-a-pdf"))

    output, complete = read_path._rehydrate_final_report(_record(), _result())

    assert complete is False
    assert output["report_artifact_status"]["pdf_integrity_verified"] is False
    assert output["report_artifact_status"]["missing_formats"] == ["pdf"]
    assert output["report_artifact_status"]["format_equivalence_ready"] is False
