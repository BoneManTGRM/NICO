from __future__ import annotations

import json

import pytest

import nico.no_server_assessment as no_server


def test_authorization_failure_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as caught:
        no_server.main(["local", "synthetic-project"])
    assert caught.value.code == 1
    assert caught.value.__suppress_context__
    output = capsys.readouterr()
    assert output.out == json.dumps({
        "status": "blocked",
        "error": "Assessment blocked. Confirm you own the target or have explicit permission by passing --authorized.",
    }, indent=2, sort_keys=True) + "\n"
    assert output.err == ""


def test_runtime_failure_exits_nonzero_without_exception_details(monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError("private underlying exception detail")

    monkeypatch.setattr(no_server, "run_local_assessment", fail)
    with pytest.raises(SystemExit) as caught:
        no_server.main(["local", "synthetic-project", "--authorized"])
    assert caught.value.code == 1
    assert caught.value.__suppress_context__
    output = capsys.readouterr()
    assert output.out == json.dumps({
        "status": "error", "error": "Assessment failed.", "error_type": "RuntimeError",
    }, indent=2, sort_keys=True) + "\n"
    assert output.err == ""
    assert "private underlying exception detail" not in output.out


def test_invalid_report_selection_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as caught:
        no_server.main(["report", "invalid-selection"])
    assert caught.value.code == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "error", "error": "Assessment failed.", "error_type": "ValueError",
    }
    assert output.err == ""


def test_successful_assessment_preserves_json(monkeypatch, capsys):
    def assess(path, authorized):
        assert path == "synthetic-project"
        assert authorized is True
        return {"status": "completed", "mode": "no-server-local-first"}

    monkeypatch.setattr(no_server, "run_local_assessment", assess)
    assert no_server.main(["local", "synthetic-project", "--authorized"]) is None
    output = capsys.readouterr()
    assert output.out == json.dumps({
        "status": "completed", "mode": "no-server-local-first",
    }, indent=2, sort_keys=True) + "\n"
    assert output.err == ""


def test_successful_report_preserves_text(monkeypatch, capsys):
    def report(fmt):
        assert fmt == "markdown"
        return "# Synthetic assessment\n\nCompleted."

    monkeypatch.setattr(no_server, "report_text", report)
    assert no_server.main(["report", "latest", "--format", "markdown"]) is None
    output = capsys.readouterr()
    assert output.out == "# Synthetic assessment\n\nCompleted.\n"
    assert output.err == ""
