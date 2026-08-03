from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import unified_production_acceptance as contract


EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
ES_BOUNDARY = (
    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
    "ENTREGA AL CLIENTE BLOQUEADA"
)


def _payload() -> dict:
    return {
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _assessment() -> dict:
    return {"client_delivery_allowed": False}


def test_automated_draft_preapproval_posture_is_accepted_across_formats() -> None:
    result = contract.validate_preapproval_delivery_posture(
        EN_BOUNDARY,
        EN_BOUNDARY,
        _payload(),
        _assessment(),
        rendered_html=f"<!doctype html><p>{EN_BOUNDARY}</p>",
    )

    assert result["automated_draft_language_verified"] is True
    assert result["pending_human_approval_verified"] is True
    assert result["client_delivery_blocked_verified"] is True
    assert result["unapproved_finality_absent"] is True


def test_spanish_automated_draft_keeps_the_same_preapproval_boundary() -> None:
    result = contract.validate_preapproval_delivery_posture(
        ES_BOUNDARY,
        ES_BOUNDARY,
        _payload(),
        _assessment(),
        rendered_html=f"<!doctype html><p>{ES_BOUNDARY}</p>",
    )

    assert result["automated_draft_language_verified"] is True
    assert result["pending_human_approval_verified"] is True
    assert result["client_delivery_blocked_verified"] is True


def test_unapproved_final_report_language_remains_fail_closed() -> None:
    value = f"FINAL REPORT · {EN_BOUNDARY}"

    with pytest.raises(AssertionError, match="unapproved finality"):
        contract.validate_preapproval_delivery_posture(
            value,
            value,
            _payload(),
            _assessment(),
            rendered_html=f"<!doctype html><p>{value}</p>",
        )


def test_retired_raw_evidence_appendix_heading_is_rejected_not_explanatory_prose() -> None:
    assert contract._retired_heading_present("## Evidence Appendix\nraw machine fields") is True
    assert contract._retired_heading_present("## Apéndice de evidencia\ncampos internos") is True
    assert (
        contract._retired_heading_present(
            "The full Evidence Appendix remains outside the bounded client PDF."
        )
        is False
    )


def test_compact_evidence_summary_and_canonical_metric_are_the_live_contract() -> None:
    source = (SCRIPTS / "unified_production_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert "COMPACT_EVIDENCE_SUMMARY_MARKERS" in source
    assert '"Evidence Package Summary"' in source
    assert '"Client Evidence Summary"' in source
    assert '"Incomplete applicable analyzers:" in content' in source
    assert "RETIRED_EVIDENCE_APPENDIX_HEADINGS" in source
    assert "AUTOMATED_DRAFT_MARKERS" in source
    assert "FORBIDDEN_UNAPPROVED_FINALITY" in source
    assert 'assert "FINAL REPORT" in upper_markdown' not in source
    assert '"Evidence Appendix",\n            "Human Review and Acceptance Gate"' not in source
