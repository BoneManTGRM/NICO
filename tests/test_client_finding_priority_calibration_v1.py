from __future__ import annotations

from pathlib import Path

from nico.client_finding_priority_calibration_v1 import (
    MODEL,
    calibrate_finding,
    calibrate_finding_register,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"


def _finding(
    *,
    finding_id: str,
    title: str,
    path: str,
    line: int,
    complexity: int,
) -> dict:
    return {
        "finding_id": finding_id,
        "finding_family": "complexity_hotspot",
        "title": title,
        "path": path,
        "line": line,
        "location": f"{path}:{line}",
        "observed_evidence": (
            f"cyclomatic_complexity={complexity}; method=typescript_compiler_ast; "
            "source=retained exact-SHA architecture evidence"
        ),
        "business_impact": "Concentrated branch logic increases regression risk.",
        "priority": "P1",
    }


def _register() -> dict:
    return {
        "code_findings": [
            _finding(
                finding_id="GENERIC-35",
                title="Reduce complexity in anonymous callback",
                path="apps/web/app/components/GenericPanel.tsx",
                line=10,
                complexity=35,
            ),
            _finding(
                finding_id="OPERATIONS-52",
                title="Reduce complexity in OperationsPage",
                path="apps/web/app/operations/page.tsx",
                line=177,
                complexity=52,
            ),
            _finding(
                finding_id="DELIVERY-31",
                title="Reduce complexity in DeliveryReadiness",
                path="apps/web/app/full-run/DeliveryReadiness.tsx",
                line=55,
                complexity=31,
            ),
            _finding(
                finding_id="FINAL-REVIEW-40",
                title="Reduce complexity in transition_final_review",
                path="nico/final_review_workflow.py",
                line=226,
                complexity=40,
            ),
        ],
        "operational_findings": [],
        "excluded_non_production_findings": [],
        "summary": {},
    }


def test_complexity_alone_does_not_create_p1() -> None:
    generic = calibrate_finding(_register()["code_findings"][0])

    assert generic["priority"] == "P2"
    assert generic["measured_cyclomatic_complexity"] == 35
    assert generic["critical_path_relevance"] == []
    assert generic["complexity_alone_created_p1"] is False
    assert "does not establish" in generic["priority_rationale"]


def test_p1_requires_critical_path_and_explicit_elevation_rationale() -> None:
    operations = calibrate_finding(_register()["code_findings"][1])
    final_review = calibrate_finding(_register()["code_findings"][3])

    assert operations["priority"] == "P1"
    assert "operations" in operations["critical_path_relevance"]
    assert operations["operations_relevance"] is True
    assert operations["measured_cyclomatic_complexity"] == 52
    assert "complexity alone did not create P1" in operations["priority_rationale"]

    assert final_review["priority"] == "P1"
    assert "delivery" in final_review["critical_path_relevance"]
    assert final_review["delivery_relevance"] is True
    assert final_review["measured_cyclomatic_complexity"] == 40
    assert final_review["priority_rationale"]


def test_delivery_path_below_p1_complexity_threshold_remains_p2() -> None:
    delivery = calibrate_finding(_register()["code_findings"][2])

    assert delivery["priority"] == "P2"
    assert delivery["delivery_relevance"] is True
    assert delivery["measured_cyclomatic_complexity"] == 31
    assert delivery["complexity_alone_created_p1"] is False


def test_register_distribution_and_top_order_are_deterministic() -> None:
    calibrated = calibrate_finding_register(_register())
    records = calibrated["code_findings"]
    summary = calibrated["summary"]

    assert [item["finding_id"] for item in records] == [
        "OPERATIONS-52",
        "FINAL-REVIEW-40",
        "GENERIC-35",
        "DELIVERY-31",
    ]
    assert summary["priority_distribution"] == {
        "P0": 0,
        "P1": 2,
        "P2": 2,
        "P3": 0,
    }
    assert summary["p1_without_rationale"] == []
    assert summary["complexity_p1_without_critical_path"] == []
    assert summary["priority_contract_verified"] is True
    assert summary["complexity_alone_creates_p1"] is False
    assert summary["priority_model_version"] == MODEL


def test_non_complexity_p1_also_receives_a_reviewable_rationale() -> None:
    finding = calibrate_finding(
        {
            "finding_id": "SECURITY-1",
            "priority": "P1",
            "title": "Confirmed authorization bypass",
            "category": "security",
            "location": "nico/auth.py:10",
            "severity": "high",
        }
    )

    assert finding["priority"] == "P1"
    assert finding["priority_rationale"]
    assert finding["priority_model_version"] == MODEL
    assert finding["complexity_alone_created_p1"] is False


def test_runtime_binds_priority_calibration_after_report_layers() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    companion = source.index("install_comprehensive_review_companion_v5()")
    priority = source.index("install_client_finding_priority_calibration_v1()")
    assert companion < priority
    assert 'RUNTIME_REVISION = "v69-evidence-based-finding-priority"' in source
    assert '"complexity_alone_creates_p1": False' in source
    assert '"p1_elevation_rationale_required": True' in source
    assert '"priority_order_deterministic": True' in source
