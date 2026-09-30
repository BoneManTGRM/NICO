import json

from nico.comprehensive_browser_continuation_dispatch_v1 import _log_continuation_failure


def test_failure_log_retains_static_code_without_dynamic_message(capsys):
    _log_continuation_failure("comprun_test", ValueError("invalid_run_record:secret-evidence"))
    output = capsys.readouterr().out
    assert "secret-evidence" not in output
    value = json.loads(output.split(" ", 1)[1])
    assert value["error_code"] == "invalid_run_record"
    assert value["error_type"] == "ValueError"
    assert value["content_retained"] is False


def test_unknown_message_cannot_be_exposed_as_code(capsys):
    _log_continuation_failure("comprun_test", RuntimeError("secret-evidence"))
    output = capsys.readouterr().out
    assert "secret-evidence" not in output
    assert json.loads(output.split(" ", 1)[1])["error_code"] == "unrecognized"
