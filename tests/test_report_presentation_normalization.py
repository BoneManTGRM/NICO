from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from nico.report_presentation_normalization import (
    deduplicate_text_items,
    normalize_report_presentation_lists,
)


ROOT = Path(__file__).resolve().parents[1]
FINAL_GATE = ROOT / "nico" / "hosted_truth_delivery_gate.py"


def test_text_deduplication_is_whitespace_case_and_unicode_compatible() -> None:
    items, removed = deduplicate_text_items(
        [
            "GitHub App installation auth not configured: app_id, private_key, installation_id.",
            "  github app installation auth NOT configured:  app_id, private_key, installation_id.  ",
            "ＧｉｔＨｕｂ App installation auth not configured: app_id, private_key, installation_id.",
        ]
    )

    assert items == ["GitHub App installation auth not configured: app_id, private_key, installation_id."]
    assert removed == 2


def test_normalizer_removes_exact_repetition_but_preserves_distinct_limitations() -> None:
    result = {
        "status": "complete",
        "unavailable_data_notes": [
            "GitHub App installation auth not configured: app_id, private_key, installation_id.",
            "Hosted scanner worker could not check out the authorized repository.",
            "GitHub App installation auth not configured: app_id, private_key, installation_id.",
            "No completed worker evidence was available to attach to this Express assessment.",
            "Export Truth Gate warnings were recorded; exports are draft-only and require human review before client delivery.",
        ],
        "sections": [],
        "maturity_signal": {"level": "Senior", "score": 86},
        "trust_level": "review_limited",
        "human_review_required": True,
        "client_ready": False,
    }

    output = normalize_report_presentation_lists(result)

    assert output["unavailable_data_notes"] == [
        "GitHub App installation auth not configured: app_id, private_key, installation_id.",
        "Hosted scanner worker could not check out the authorized repository.",
        "No completed worker evidence was available to attach to this Express assessment.",
        "Export Truth Gate warnings were recorded; exports are draft-only and require human review before client delivery.",
    ]
    guard = output["report_quality_guards"]["presentation_list_normalization"]
    assert guard["status"] == "normalized"
    assert guard["duplicates_removed"] == 1
    assert output["maturity_signal"] == {"level": "Senior", "score": 86}
    assert output["trust_level"] == "review_limited"
    assert output["human_review_required"] is True
    assert output["client_ready"] is False


def test_normalizer_cleans_section_and_nested_assessment_presentation_lists() -> None:
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "velocity_complexity",
                "score": 79,
                "status": "yellow",
                "evidence": ["Commit velocity is available.", "Commit velocity is available."],
                "findings": ["Same-run complexity is unavailable.", "Same-run complexity is unavailable."],
                "unavailable": [
                    "Maintainability requires a valid analyzer artifact.",
                    "Maintainability requires a valid analyzer artifact.",
                    "Story-point expectations require stakeholder context.",
                ],
            }
        ],
        "assessment": {
            "unavailable_data_notes": ["Approval is unavailable.", " approval is unavailable. "],
            "sections": [
                {
                    "id": "client_acceptance",
                    "evidence": ["Human review required.", "Human review required."],
                    "findings": [],
                    "unavailable": ["Client approval not recorded.", "Client approval not recorded."],
                }
            ],
        },
    }

    output = normalize_report_presentation_lists(result)

    velocity = output["sections"][0]
    assert velocity["evidence"] == ["Commit velocity is available."]
    assert velocity["findings"] == ["Same-run complexity is unavailable."]
    assert velocity["unavailable"] == [
        "Maintainability requires a valid analyzer artifact.",
        "Story-point expectations require stakeholder context.",
    ]
    assert output["assessment"]["unavailable_data_notes"] == ["Approval is unavailable."]
    assert output["assessment"]["sections"][0]["evidence"] == ["Human review required."]
    assert output["assessment"]["sections"][0]["unavailable"] == ["Client approval not recorded."]
    assert output["report_quality_guards"]["presentation_list_normalization"]["duplicates_removed"] == 6


def test_normalizer_does_not_mutate_raw_artifacts_or_ledgers() -> None:
    raw = {
        "unavailable_data_notes": ["raw duplicate", "raw duplicate"],
        "nested": {"evidence": ["raw evidence", "raw evidence"]},
    }
    result = {
        "status": "complete",
        "unavailable_data_notes": ["presentation duplicate", "presentation duplicate"],
        "scanner_worker_artifact": deepcopy(raw),
        "evidence_ledger": deepcopy(raw),
        "sections": [],
    }

    output = normalize_report_presentation_lists(result)

    assert output["unavailable_data_notes"] == ["presentation duplicate"]
    assert output["scanner_worker_artifact"] == raw
    assert output["evidence_ledger"] == raw


def test_final_hosted_gate_normalizes_before_report_rebuild_and_after_export_gate() -> None:
    source = FINAL_GATE.read_text(encoding="utf-8")

    before_rebuild = source.index("result = normalize_report_presentation_lists(result)\n    apply_pdf_display_patch()")
    rebuild = source.index("result = rebuild_reports(result)")
    export_gate = source.index("result = apply_export_truth_gate(result)")
    after_export = source.index("result = normalize_report_presentation_lists(result)", before_rebuild + 1)

    assert before_rebuild < rebuild < export_gate < after_export
    assert "Semantically distinct limitations are preserved" not in source
