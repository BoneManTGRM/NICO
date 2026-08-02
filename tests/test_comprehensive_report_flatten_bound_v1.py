from __future__ import annotations

import time

from nico import comprehensive_report_package as report_module
from nico.comprehensive_report_flatten_bound_v1 import (
    MAX_FLATTEN_VISITS,
    install_bounded_report_flatten,
)


def test_bounded_flatten_stops_deep_non_emitting_payloads() -> None:
    install_bounded_report_flatten()
    huge = [
        {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "level_4": {
                            "level_5": {
                                "level_6": [
                                    {"path": f"file_{index}_{nested}"}
                                    for nested in range(10)
                                ]
                            }
                        }
                    }
                }
            }
        }
        for index in range(50_000)
    ]
    started = time.perf_counter()

    result = report_module._flatten(huge, prefix="huge", maximum=120)

    assert time.perf_counter() - started < 3.0
    assert len(result) <= 120
    assert MAX_FLATTEN_VISITS == 6_000


def test_normal_flatten_output_contract_is_preserved() -> None:
    install_bounded_report_flatten()
    value = {
        "coverage": 100,
        "tools": ["pip-audit", "bandit"],
        "nested": {"status_detail": "complete"},
    }

    result = report_module._flatten(value, prefix="evidence", maximum=20)

    assert "evidence.coverage: 100" in result
    assert "evidence.tools[0]: pip-audit" in result
    assert "evidence.tools[1]: bandit" in result
    assert "evidence.nested.status_detail: complete" in result
