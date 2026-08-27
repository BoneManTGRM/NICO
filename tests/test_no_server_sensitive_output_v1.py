from __future__ import annotations

import json
from pathlib import Path

import nico.no_server_assessment as no_server


class _FakeStore:
    def save_report(self, *_args, **_kwargs) -> None:
        return None

    def audit(self, *_args, **_kwargs) -> None:
        return None


def _report(secret: str) -> dict:
    return {
        "target": f"https://user:{secret}@example.com/repo?token={secret}",
        "assessment_id": "assessment_test",
        "created_at": "2026-08-27T00:00:00+00:00",
        "mode": "no-server-local-first",
        "target_type": "url",
        "executive_summary": f"Credential evidence api_key={secret}",
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
        "evidence_log": [f"password={secret}"],
        "unavailable_data_notes": [],
        "token": secret,
        "nested": {"private_key": secret, "safe": f"secret={secret}"},
    }


def test_sanitize_output_redacts_sensitive_keys_and_url_userinfo() -> None:
    secret = "supersecretvalue12345"
    sanitized = no_server.sanitize_output(_report(secret))
    serialized = json.dumps(sanitized, sort_keys=True)

    assert secret not in serialized
    assert "user:" not in sanitized["target"]
    assert sanitized["token"] == "***REDACTED***"
    assert sanitized["nested"]["private_key"] == "***REDACTED***"
    assert sanitized["authorization_scope"] == "Explicitly authorized assessment scope."


def test_write_latest_reports_never_persists_raw_sensitive_values(tmp_path: Path, monkeypatch) -> None:
    secret = "supersecretvalue12345"
    monkeypatch.setattr(no_server, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(no_server, "Store", _FakeStore)

    paths = no_server.write_latest_reports(_report(secret))

    for path in paths.values():
        text = Path(path).read_text(encoding="utf-8")
        assert secret not in text
        assert f"user:{secret}@" not in text


def test_print_json_never_logs_raw_sensitive_values(capsys) -> None:
    secret = "supersecretvalue12345"
    no_server.print_json({"token": secret, "message": f"api_key={secret}"})

    output = capsys.readouterr().out
    assert secret not in output
    assert "***REDACTED***" in output
