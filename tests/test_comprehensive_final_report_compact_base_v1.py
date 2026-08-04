from __future__ import annotations

import base64
import time

from pypdf import PdfReader

from nico import comprehensive_native_providers as native
from nico import comprehensive_report_package as report_module
from nico.comprehensive_final_report_compact_base_v1 import (
    VERSION,
    install_comprehensive_final_report_compact_base_v1,
)


def _identity() -> dict[str, str]:
    return {
        "run_id": "comprun_compact_base",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "2c059af469fedcf3664a3f431fd1a51bcb145f91",
        "evidence_ledger_id": "ledger_compact_base",
        "customer_id": "customer",
        "project_id": "project",
    }


def _assessment() -> dict:
    return {
        "status": "complete",
        "maturity_signal": {
            "level": "Strong",
            "score": 88,
            "presented_score": 88,
        },
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "status": "strong",
                "presented_status": "strong",
                "score": 88,
                "presented_score": 88,
                "summary": "Architecture evidence retained.",
                "evidence": ["Exact-source complexity evidence retained."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "unavailable_data_notes": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _stage_results(count: int = 19, evidence_items: int = 100) -> dict[str, dict]:
    stages: dict[str, dict] = {}
    for index in range(count):
        stages[f"synthetic_stage_{index:02d}"] = {
            "status": "complete",
            "summary": f"Stage {index} retained bounded evidence.",
            "evidence": {
                "items": [
                    f"retained evidence {index}:{item}"
                    for item in range(evidence_items)
                ]
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    stages["evidence_reconciliation_and_scoring"] = {
        "status": "complete",
        "assessment": _assessment(),
        "evidence": {"technical_score": 88},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return stages


def test_final_build_omits_disposable_raw_stage_appendix_but_retains_json(monkeypatch) -> None:
    observed_stage_counts: list[int] = []

    def fake_pdf(identity, assessment, stages, generated_at):
        observed_stage_counts.append(len(stages))
        return base64.b64encode(b"%PDF-1.4\n%%EOF").decode("ascii"), None, 1

    def fake_build(context, final):
        encoded, error, pages = report_module._pdf(
            _identity(),
            _assessment(),
            [{"stage_id": "a"}, {"stage_id": "b"}],
            "2026-08-04T00:00:00Z",
        )
        return {
            "status": "complete",
            "report_package": {
                "pdf_base64": encoded,
                "pdf_error": error,
                "pdf_page_count": pages,
                "json": {"stage_summaries": [{"stage_id": "a"}, {"stage_id": "b"}]},
            },
            "evidence": {},
        }

    monkeypatch.setattr(report_module, "_pdf", fake_pdf)
    monkeypatch.setattr(native, "_build_report", fake_build)
    installation = install_comprehensive_final_report_compact_base_v1()

    final_result = native._build_report({}, True)
    decision_result = native._build_report({}, False)

    assert observed_stage_counts == [0, 2]
    assert final_result["report_package"]["json"]["stage_summaries"] == [
        {"stage_id": "a"},
        {"stage_id": "b"},
    ]
    projection = final_result["final_report_compact_base"]
    assert projection["artifact_schema"] == VERSION
    assert projection["raw_stage_appendix_rendered_in_intermediate_pdf"] is False
    assert projection["full_stage_evidence_retained_in_canonical_json"] is True
    assert projection["full_stage_evidence_retained_in_durable_run"] is True
    assert projection["client_delivery_allowed"] is False
    assert "final_report_compact_base" not in decision_result
    assert installation["score_contract_changed"] is False
    assert installation["report_design_changed"] is False


def test_real_final_base_build_is_bounded_and_keeps_full_stage_summaries() -> None:
    install_comprehensive_final_report_compact_base_v1()
    context = {
        **_identity(),
        "prior_stage_results": _stage_results(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    started = time.perf_counter()
    result = native._build_report(context, True)
    elapsed = time.perf_counter() - started

    assert result["status"] == "complete"
    package = result["report_package"]
    pdf = base64.b64decode(package["pdf_base64"])
    assert pdf.startswith(b"%PDF")
    assert len(PdfReader(__import__("io").BytesIO(pdf)).pages) < 15
    assert len(package["json"]["stage_summaries"]) == len(_stage_results())
    assert result["final_report_compact_base"][
        "raw_stage_appendix_rendered_in_intermediate_pdf"
    ] is False
    assert elapsed < 20


def test_decision_report_build_keeps_existing_stage_pdf_projection() -> None:
    install_comprehensive_final_report_compact_base_v1()
    context = {
        **_identity(),
        "prior_stage_results": _stage_results(count=3, evidence_items=2),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    result = native._build_report(context, False)

    assert result["status"] == "complete"
    assert "final_report_compact_base" not in result
    assert result["report_package"]["pdf_page_count"] >= 3
    assert result["client_delivery_allowed"] is False
