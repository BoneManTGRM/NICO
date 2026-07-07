from __future__ import annotations

from typing import Any

from nico.status_output import attach_status_output


def attach_assessment_status_output(result: dict[str, Any]) -> dict[str, Any]:
    return attach_status_output(result)


def attach_report_status_output(result: dict[str, Any]) -> dict[str, Any]:
    return attach_status_output(result)
