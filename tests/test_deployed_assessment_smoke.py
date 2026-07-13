from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deployed_assessment_smoke.py"
SPEC = importlib.util.spec_from_file_location("deployed_assessment_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_mid_starts_once_and_polls_only_returned_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    responses = iter(
        [
            {"status": "running", "run_id": "mid_123"},
            {"status": "running", "run_id": "mid_123"},
            {"status": "complete", "run_id": "mid_123"},
        ]
    )

    def fake_request(_base_url: str, path: str, _payload: dict, _token: str) -> dict:
        calls.append(path)
        return next(responses)

    monkeypatch.setattr(smoke, "_json_request", fake_request)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    result = smoke.run_tier(
        "https://api.example.test",
        smoke.TIERS["mid"],
        {"repository": "owner/repo", "authorized": True},
        "",
        0,
        3,
    )

    assert result == {"tier": "mid", "run_id": "mid_123", "status": "complete", "polls": 2}
    assert calls == [
        "/assessment/mid-run",
        "/assessment/mid-run/mid_123/status",
        "/assessment/mid-run/mid_123/status",
    ]


def test_status_identity_change_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {"status": "running", "run_id": "full_original"},
            {"status": "running", "run_id": "full_replacement"},
        ]
    )

    monkeypatch.setattr(smoke, "_json_request", lambda *_args: next(responses))
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    with pytest.raises(smoke.SmokeFailure, match="changed run identity"):
        smoke.run_tier(
            "https://api.example.test",
            smoke.TIERS["full"],
            {"repository": "owner/repo", "authorized": True},
            "",
            0,
            1,
        )


def test_missing_run_id_fails_without_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_request(*_args) -> dict:
        nonlocal calls
        calls += 1
        return {"status": "running"}

    monkeypatch.setattr(smoke, "_json_request", fake_request)

    with pytest.raises(smoke.SmokeFailure, match="omitted run_id"):
        smoke.run_tier(
            "https://api.example.test",
            smoke.TIERS["mid"],
            {"repository": "owner/repo", "authorized": True},
            "",
            0,
            3,
        )

    assert calls == 1


def test_full_start_preserves_full_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[dict] = []

    def fake_request(_base_url: str, _path: str, payload: dict, _token: str) -> dict:
        observed.append(dict(payload))
        return {"status": "complete", "run_id": "full_123"}

    monkeypatch.setattr(smoke, "_json_request", fake_request)

    smoke.run_tier(
        "https://api.example.test",
        smoke.TIERS["full"],
        {"repository": "owner/repo", "authorized": True},
        "",
        0,
        1,
    )

    assert observed[0]["mode"] == "full"
    assert observed[0]["build_reports"] is True
    assert observed[0]["create_final_review_request"] is True
