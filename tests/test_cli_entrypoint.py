from __future__ import annotations

import json
from pathlib import Path

import pytest

import nico.cli_entrypoint as entrypoint


ROOT = Path(__file__).resolve().parents[1]
MAIN_MODULE = ROOT / "nico" / "__main__.py"


def test_parser_exposes_the_canonical_command_set() -> None:
    parser = entrypoint.build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )

    assert tuple(subparsers.choices) == entrypoint.CLI_COMMANDS
    assert entrypoint.CLI_COMMANDS == (
        "scan",
        "scan-test-lab",
        "scan-drift-demo",
        "report",
        "verify",
        "memory",
        "policy",
        "scanner-availability",
        "assessment",
    )


def test_scan_dispatch_preserves_the_compact_cli_summary(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        entrypoint,
        "run_scan",
        lambda target: {
            "scan": {"id": "scan_exact_1", "findings": [{}, {}]},
            "drift": [{}],
            "repairs": [{}, {}, {}],
            "target": target,
        },
    )

    entrypoint.main(["scan", "authorized/repository"])

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "scan_id": "scan_exact_1",
        "findings": 2,
        "drift": 1,
        "repairs": 3,
    }


def test_report_dispatch_keeps_specialized_and_generated_paths_separate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    specialized_calls: list[str] = []
    generated_calls: list[bool] = []
    monkeypatch.setattr(
        entrypoint,
        "report_text",
        lambda kind: specialized_calls.append(kind) or f"report:{kind}",
    )
    monkeypatch.setattr(
        entrypoint,
        "generate_reports",
        lambda: generated_calls.append(True) or [{"format": "json", "path": "synthetic.json"}],
    )

    entrypoint.main(["report", "owner"])
    owner_output = capsys.readouterr().out.strip()
    entrypoint.main(["report", "latest"])
    latest_output = json.loads(capsys.readouterr().out)

    assert owner_output == "report:owner"
    assert specialized_calls == ["owner"]
    assert generated_calls == [True]
    assert latest_output == [{"format": "json", "path": "synthetic.json"}]


def test_verify_dispatch_uses_exact_repair_id_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requested: list[str] = []
    monkeypatch.setattr(entrypoint, "verify_latest", lambda: {"status": "latest"})
    monkeypatch.setattr(
        entrypoint,
        "verify_repair_by_id",
        lambda repair_id: requested.append(repair_id) or {"status": "repair", "repair_id": repair_id},
    )

    entrypoint.main(["verify", "latest", "--repair-id", "repair_exact_1"])

    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "repair", "repair_id": "repair_exact_1"}
    assert requested == ["repair_exact_1"]


def test_policy_store_is_created_only_for_policy_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stores: list[bool] = []

    class FakeStore:
        def __init__(self) -> None:
            stores.append(True)

        def policy(self) -> dict[str, object]:
            return {"autonomy_level": 1, "kill_switch": False}

    monkeypatch.setattr(entrypoint, "Store", FakeStore)
    monkeypatch.setattr(entrypoint, "scanner_availability", lambda: [])

    entrypoint.main(["scanner-availability"])
    assert json.loads(capsys.readouterr().out) == []
    assert stores == []

    entrypoint.main(["policy"])
    assert json.loads(capsys.readouterr().out) == {
        "autonomy_level": 1,
        "kill_switch": False,
    }
    assert stores == [True]


def test_package_main_uses_extracted_cli_entrypoint_and_preserves_assess_dispatch() -> None:
    source = MAIN_MODULE.read_text(encoding="utf-8")

    assert "from nico.cli_entrypoint import main as cli_main" in source
    assert "from nico.cli import main as cli_main" not in source
    assert 'sys.argv[1] == "assess"' in source
    assert "assess_main(sys.argv[2:])" in source


def test_invalid_assessment_tier_remains_parser_blocked() -> None:
    with pytest.raises(SystemExit) as error:
        entrypoint.main(["assessment", "authorized/repository", "--tier", "enterprise"])

    assert error.value.code == 2
