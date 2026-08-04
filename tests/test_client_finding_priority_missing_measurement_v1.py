from __future__ import annotations

from nico.client_finding_priority_calibration_v1 import calibrate_finding


def test_missing_numeric_complexity_measurement_stays_provisional_p2() -> None:
    finding = calibrate_finding(
        {
            "finding_id": "NICO-FINDING-MISSING-MEASUREMENT",
            "priority": "P1",
            "finding_family": "complexity_hotspot",
            "title": "Reduce complexity in OperationsPage",
            "path": "apps/web/app/operations/page.tsx",
            "line": 177,
            "location": "apps/web/app/operations/page.tsx:177",
            "observed_evidence": (
                "The canonical finding was retained against the assessed immutable commit."
            ),
            "business_impact": (
                "Requires human technical disposition before the condition can be treated as resolved."
            ),
        }
    )

    assert finding["priority"] == "P2"
    assert finding["measured_cyclomatic_complexity"] == 0
    assert finding["complexity_measurement_retained"] is False
    assert finding["technical_severity"] == "unknown"
    assert "numeric complexity measurement was not retained" in finding[
        "priority_rationale"
    ]
    assert finding["complexity_alone_created_p1"] is False
