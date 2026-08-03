from __future__ import annotations

from nico.comprehensive_decision_content_restoration_v67 import (
    restore_decision_content,
)


def test_restoration_ignores_unrelated_large_stage_payloads() -> None:
    unrelated = {
        "payload": [
            {"noise": index, "nested": {"more_noise": "x" * 50}}
            for index in range(5000)
        ]
    }
    raw_stages = {
        "unrelated_large_stage": unrelated,
        "repository_and_delivery_evidence": {
            "complexity_evidence": {
                "hotspots": [
                    {
                        "path": "nico/report.py",
                        "line": 40,
                        "end_line": 140,
                        "name": "build_report",
                        "cyclomatic_complexity": 61,
                        "method": "python_ast",
                    }
                ]
            }
        },
    }

    canonical, _assessment, manifest = restore_decision_content(
        {"assessment": {}},
        raw_stages=raw_stages,
        assessment={},
        commit_sha="a" * 40,
    )

    assert len(canonical["canonical_findings"]) == 1
    assert manifest["source_stage_population"] == 2
    assert manifest["selected_stage_population"] == 1
    assert manifest["selected_stage_ids"] == ["repository_and_delivery_evidence"]
    assert manifest["unrelated_stage_payloads_not_copied_or_scanned"] is True
