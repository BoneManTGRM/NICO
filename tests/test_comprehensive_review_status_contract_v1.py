from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "comprehensive_review_status_contract_v1.py"
SPEC = importlib.util.spec_from_file_location(
    "comprehensive_review_status_contract_v1_test",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def _section(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "label": "Static Analysis",
        "presented_score": 96,
        "presented_status": "Provisional Strong — Human Review Required",
        "human_review_required": True,
        "review_required_candidates": 581,
        "assurance_status": "human_review_required",
        "score_effect": "assurance-only until triaged",
        "score_contract": {
            "review_required_count": 581,
            "unverified_candidate_volume_affects_assurance_only": True,
            "unverified_candidate_volume_affects_technical_score": False,
        },
    }
    value.update(overrides)
    return value


def test_accepts_live_provisional_status_when_all_review_gates_are_bound() -> None:
    section = _section()
    assert contract.assert_section_status_contract(
        section,
        label="Static Analysis",
        score=96,
        status=str(section["presented_status"]),
        numeric_status="STRONG",
    ) == "PROVISIONAL STRONG — HUMAN REVIEW REQUIRED"


def test_accepts_numeric_status_when_no_review_candidates_exist() -> None:
    section = _section(
        presented_status="Strong",
        review_required_candidates=0,
        score_contract={"review_required_count": 0},
        assurance_status="green",
        human_review_required=False,
        score_effect="verified material only",
    )
    assert contract.assert_section_status_contract(
        section,
        label="Code Audit",
        score=96,
        status="STRONG",
        numeric_status="STRONG",
    ) == "STRONG"


def test_rejects_stale_strong_status_when_candidates_require_review() -> None:
    with pytest.raises(AssertionError, match="expected PROVISIONAL STRONG"):
        contract.assert_section_status_contract(
            _section(presented_status="STRONG"),
            label="Static Analysis",
            score=96,
            status="STRONG",
            numeric_status="STRONG",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"human_review_required": False}, "mandatory human review"),
        ({"assurance_status": "review_limited"}, "unsupported assurance status"),
        ({"score_effect": "technical score reduced", "score_contract": {}}, "assurance-only scoring"),
    ],
)
def test_rejects_provisional_status_without_complete_evidence_contract(
    overrides: dict[str, object],
    message: str,
) -> None:
    section = _section(**overrides)
    with pytest.raises(AssertionError, match=message):
        contract.assert_section_status_contract(
            section,
            label="Static Analysis",
            score=96,
            status=str(section["presented_status"]),
            numeric_status="STRONG",
        )


def test_rejects_provisional_contract_for_non_strong_numeric_band() -> None:
    with pytest.raises(AssertionError, match="no authorized provisional contract"):
        contract.assert_section_status_contract(
            _section(presented_score=78),
            label="Architecture & Technical Debt",
            score=78,
            status="PROVISIONAL STRONG — HUMAN REVIEW REQUIRED",
            numeric_status="MODERATE",
        )


def test_spanish_provisional_status_is_supported_with_same_evidence() -> None:
    section = _section(
        presented_status="Fuerte provisional — Revisión humana requerida"
    )
    assert contract.assert_section_status_contract(
        section,
        label="Análisis estático",
        score=96,
        status=str(section["presented_status"]),
        numeric_status="STRONG",
    ) == "FUERTE PROVISIONAL — REVISIÓN HUMANA REQUERIDA"


def test_authoritative_runner_binds_provisional_contract_and_proof_key() -> None:
    source = (
        ROOT / "scripts" / "unified_production_acceptance_authoritative.py"
    ).read_text(encoding="utf-8")
    assert "from comprehensive_review_status_contract_v1 import assert_section_status_contract" in source
    assert "status = assert_section_status_contract(" in source
    assert '"provisional_review_status_contract_verified": True' in source
    assert "status == expected" not in source
