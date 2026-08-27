from __future__ import annotations

# Regression coverage for sensitive-output sanitization and CodeQL verification.

import json
from pathlib import Path

import nico.no_server_assessment as no_server


class _FakeStore:
    def save_report(self, *_args, **_kwargs) -> None:
        return None

    def audit(self, *_args, **_kwargs) -> None:
        return None


def _report(fixture_value: str) -> dict:
    return {
        "target": f"https://user:{fixture_value}@example.com/repo?token={fixture_value}",
        "assessment_id": "assessment_test",
        "created_at": "2026-08-27T00:00:00+00:00",
        "mode": "no-server-local-first",
        "target_type": "url",
        "executive_summary": f"Credential evidence api_key={fixture_value}",
        "authorization_scope": "Explicitly authorized assessment scope.",
        "safety_boundary": "Defensive-only.",
        "target_summary": {},
        "maturity_semaphore": {},
        "sections": [],
        "bug_risk_findings": [],
        "repair_recommendations": [],
        "verification_checklist": [],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "evidence_log": [f"password={fixture_value}"],
        "unavailable_data_notes": [],
        "token": fixture_value,
        "nested": {"private_key": fixture_value, "safe": f"secret={fixture_value}"},
    }


def test_sanitize_output_redacts_sensitive_keys_and_url_userinfo() -> None:
    fixture_value = "supersecretvalue12345"
    sanitized = no_server.sanitize_output(_report(fixture_value))
    serialized = json.dumps(sanitized, sort_keys=True)

    assert fixture_value not in serialized
    assert "user:" not in sanitized["target"]
    assert sanitized["token"] == "***REDACTED***"
    assert sanitized["nested"]["private_key"] == "***REDACTED***"
    assert sanitized["authorization_scope"] == "Explicitly authorized assessment scope."


def test_write_latest_reports_never_persists_raw_sensitive_values(tmp_path: Path, monkeypatch) -> None:
    fixture_value = "supersecretvalue12345"
    monkeypatch.setattr(no_server, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(no_server, "Store", _FakeStore)

    paths = no_server.write_latest_reports(_report(fixture_value))

    for path in paths.values():
        text = Path(path).read_text(encoding="utf-8")
        assert fixture_value not in text
        assert f"user:{fixture_value}@" not in text


def test_print_json_never_logs_raw_sensitive_values(capsys) -> None:
    fixture_value = "supersecretvalue12345"
    no_server.print_json({"token": fixture_value, "message": f"api_key={fixture_value}"})

    output = capsys.readouterr().out
    assert fixture_value not in output
    assert "***REDACTED***" in output
