from __future__ import annotations

from nico.full_assessment_api import FullAssessmentRequest, FullAssessmentStatusRequest
from nico.full_assessment_scanner_contract import DEFAULT_FULL_SCANNERS, _requested_tools


def _payload(model):
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def test_full_api_request_defaults_to_full_mode() -> None:
    request = FullAssessmentRequest()

    assert request.mode == "full"
    assert _payload(request)["mode"] == "full"


def test_full_status_refresh_defaults_to_full_mode() -> None:
    request = FullAssessmentStatusRequest()

    assert request.mode == "full"
    assert _payload(request)["mode"] == "full"


def test_empty_full_api_tool_selection_expands_to_complete_full_contract() -> None:
    request = FullAssessmentRequest()
    requested = _requested_tools(_payload(request))

    assert requested == list(DEFAULT_FULL_SCANNERS)
    assert requested == [
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    ]
