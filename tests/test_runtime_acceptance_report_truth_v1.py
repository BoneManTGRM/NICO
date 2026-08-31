from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_client_review_companion_v5 import (
    substantive_review_sections,
)
from nico.comprehensive_report_review_integrity_v1 import _runtime_acceptance


def canonical_with_observations() -> dict:
    return {
        "assessment": {"stage_summaries": []},
        "stage_summaries": [
            {
                "stage_id": "functional_qa",
                "status": "unavailable",
                "summary": "Repository-only functional evidence.",
                "evidence": [],
            },
            {
                "stage_id": "platform_parity",
                "status": "unavailable",
                "summary": "Repository-only platform evidence.",
                "evidence": [],
            },
            {
                "stage_id": "client_human_evidence_functional_qa_1",
                "status": "complete",
                "evidence": [
                    "Client-supplied data · Observed results: PASS",
                    "Client-supplied data · Test cases: Login and report download",
                ],
            },
            {
                "stage_id": "client_human_evidence_platform_parity_1",
                "status": "complete",
                "evidence": [
                    "Client-supplied data · Matrix: Desktop Safari English PASS",
                    "Client-supplied data · Matrix: iPhone WebKit es-MX PASS",
                ],
            },
        ],
    }


def by_id(canonical: dict, *, spanish: bool) -> dict[str, dict]:
    return {
        section["id"]: section
        for section in substantive_review_sections(canonical, spanish=spanish)
    }


def test_observed_pass_is_not_collapsed_to_not_assessed() -> None:
    sections = by_id(canonical_with_observations(), spanish=False)
    functional = sections["functional_qa"]
    assert functional["status"] == (
        "Observed runtime evidence — independent verification pending"
    )
    assert "Observed runtime evidence: PASS" in functional["evidence"]
    assert "Independent verification: Pending" in functional["evidence"]
    assert (
        "Broader production acceptance: Not yet established"
        in functional["evidence"]
    )
    assert "Not assessed — runtime evidence required" not in functional["status"]


def test_platform_observations_remain_dimensioned_until_independently_verified() -> None:
    sections = by_id(canonical_with_observations(), spanish=False)
    platform = sections["platform_parity"]
    assert "Desktop browser: Observed — independent verification pending" in (
        platform["evidence"]
    )
    assert "Mobile browser: Observed — independent verification pending" in (
        platform["evidence"]
    )
    assert "English: Observed — independent verification pending" in (
        platform["evidence"]
    )
    assert "es-MX: Observed — independent verification pending" in (
        platform["evidence"]
    )
    assert "Cross-platform parity: Not established" in platform["evidence"]


def test_independent_four_matrix_proof_establishes_parity_without_human_approval() -> None:
    canonical = deepcopy(canonical_with_observations())
    canonical["production_acceptance"] = {
        "functional_qa": {
            "independent_verification": "verified",
            "broader_production_acceptance": "proven",
        },
        "desktop": {"status": "verified"},
        "mobile": {"status": "verified"},
        "english": {"status": "verified"},
        "es_mx": {"status": "verified"},
    }
    sections = by_id(canonical, spanish=False)
    assert "Independent verification: Verified" in sections["functional_qa"][
        "evidence"
    ]
    assert "Broader production acceptance: Proven" in sections["functional_qa"][
        "evidence"
    ]
    assert "Cross-platform parity: Established" in sections["platform_parity"][
        "evidence"
    ]
    assert canonical.get("human_review_completed") is not True
    assert canonical.get("client_delivery_allowed") is not True


def test_spanish_runtime_truth_is_authored_spanish_not_translated_client_values() -> None:
    sections = by_id(canonical_with_observations(), spanish=True)
    assert "Evidencia de ejecución observada: PASS" in sections["functional_qa"][
        "evidence"
    ]
    assert "Verificación independiente: Pendiente" in sections["functional_qa"][
        "evidence"
    ]
    assert "Paridad entre plataformas: No establecida" in sections[
        "platform_parity"
    ]["evidence"]


def test_exclusion_rationale_is_not_misreported_as_runtime_observation() -> None:
    canonical = canonical_with_observations()
    canonical["stage_summaries"] = [
        {
            "stage_id": "client_human_evidence_functional_qa_1",
            "status": "excluded",
            "evidence": ["Client supplied exclusion rationale: not in scope"],
        },
        {
            "stage_id": "client_human_evidence_platform_parity_1",
            "status": "excluded_from_scope",
            "evidence": ["Client supplied exclusion rationale: not in scope"],
        },
    ]
    sections = by_id(canonical, spanish=False)
    assert "Observed runtime evidence" not in sections["functional_qa"]["status"]
    assert "Platform observations supplied" not in sections["platform_parity"][
        "status"
    ]
    assert _runtime_acceptance(canonical, spanish=False) == "Excluded"
    assert _runtime_acceptance(canonical, spanish=True) == "Excluida"
