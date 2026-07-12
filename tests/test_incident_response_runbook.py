from __future__ import annotations

from pathlib import Path


def test_incident_response_runbook_defines_required_operational_boundaries() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "INCIDENT_RESPONSE.md"
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()

    for heading in [
        "### p0",
        "### p1",
        "### p2",
        "### p3",
        "## detection and triage",
        "## containment",
        "## recovery",
        "## rollback",
        "## closure and follow-up",
        "## retention and redaction",
    ]:
        assert heading in lowered

    assert "x-nico-correlation-id" in lowered
    assert "/operations/observability" in lowered
    assert "/operations/events" in lowered
    assert "/operations/readiness" in lowered
    assert "last-known-good" in lowered
    assert "production release gate" in lowered
    assert "fresh mid or full acceptance run" in lowered
    assert "http 200 is not sufficient" in lowered

    for forbidden_storage in [
        "request or response bodies",
        "query values",
        "cookies",
        "authorization headers",
        "admin tokens",
        "api keys",
        "raw exception messages",
    ]:
        assert forbidden_storage in lowered

    assert "do not delete evidence" in lowered
    assert "do not describe degraded scanner or provider state as clean evidence" in lowered
    assert "client delivery" in lowered
