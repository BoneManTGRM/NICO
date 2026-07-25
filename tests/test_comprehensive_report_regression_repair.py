from __future__ import annotations

from nico.comprehensive_report_polish_v1 import polish_assessment


def test_raw_osv_runtime_diagnostic_is_not_used_as_client_facing_title() -> None:
    assessment = {
        "findings_register": [
            {
                "id": "osv-runtime",
                "priority": "P1",
                "category": "dependency",
                "title": (
                    "Scanning dir . Starting filesystem walk for root: / Scanned "
                    "/tmp/nico-snapshot-scan-example/repo/requirements.txt file and found 14 packages "
                    "End status: 9 dirs visited, 29 inodes visited, 1 Extract calls, 530.806µs elapsed"
                ),
                "location": "Location not retained by the scanner result.",
                "evidence": "tool=osv-scanner; category=dependency; severity=unknown; verified=False",
            }
        ]
    }

    polished = polish_assessment(assessment)
    finding = polished["findings_register"][0]

    assert finding["title"] == "OSV dependency scan did not produce a complete result"
    assert finding["priority"] == "P2"
    assert finding["location"] == "Dependency scanner execution boundary"
    assert "/tmp/nico-snapshot-scan" not in str(finding)
    assert "530.806" not in str(finding)


def test_polish_contract_records_scanner_diagnostic_cleanup() -> None:
    polished = polish_assessment({"findings_register": []})
    contract = polished["comprehensive_report_polish"]

    assert contract["temporary_scanner_paths_removed"] is True
    assert contract["scanner_timing_noise_removed"] is True
    assert contract["raw_scanner_failures_summarized"] is True
