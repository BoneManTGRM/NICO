from __future__ import annotations

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_spanish_publication_preflight_v93 import (
    inspect_spanish_canonical_publication_preflight,
)


def test_duplicate_restoration_surfaces_do_not_hide_distinct_missing_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = "The exact same untranslated acceptance sentence remains."
    second = "The second untranslated rollback sentence remains after verification."

    def fail_closed(value: str, key: str) -> str:
        if value in {first, second}:
            raise ValueError(f"missing Spanish presentation translation for {key}: {value}")
        return value

    monkeypatch.setattr(canonical, "_translate_presentation_field", fail_closed)
    finding = {
        "acceptance_criteria": [first],
        "rollback": second,
    }
    report = {
        "report_language": "es-MX",
        "identity": {"report_language": "es-MX"},
        # Restoration intentionally projects the same finding onto several client-truth
        # surfaces. Only unique field/value contracts should consume the failure budget.
        "findings_register": [finding],
        "executive_risk_register": [dict(finding)],
        "priority_findings": [dict(finding)],
        "assessment": {
            "report_language": "es-MX",
            "findings_register": [dict(finding)],
        },
    }

    manifest = inspect_spanish_canonical_publication_preflight(report)

    assert manifest["status"] == "blocked"
    assert manifest["failure_count"] == 2
    assert manifest["duplicate_contracts_skipped"] >= 4
    assert manifest["duplicate_restoration_surfaces_deduplicated"] is True
    assert {item["source"] for item in manifest["failure_details"]} == {first, second}
