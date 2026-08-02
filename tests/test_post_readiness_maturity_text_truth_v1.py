from __future__ import annotations

from nico.comprehensive_post_readiness_maturity_truth_v2 import (
    install_post_readiness_maturity_truth,
    synchronize_explicit_maturity_text,
)

INSTALLATION = install_post_readiness_maturity_truth()

from nico.comprehensive_client_readiness_v59 import reconcile_client_readiness


def _canonical() -> dict:
    return {
        "service_id": "comprehensive",
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_post_readiness_maturity",
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 91,
            "maturity_level": "Senior",
            "maturity_signal": {
                "level": "Senior",
                "label": "Senior",
                "score": 93,
            },
            "sections": [],
        },
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "status": "complete",
                "evidence": [
                    "assessment.maturity_level: Senior",
                    "maturity label = Senior",
                    "Senior engineering reviewer required",
                ],
            }
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_post_readiness_installer_is_bound() -> None:
    assert INSTALLATION["bound"] is True
    assert INSTALLATION["post_readiness_boundary"] is True
    assert INSTALLATION["strict_semantic_validation_preserved"] is True


def test_explicit_maturity_text_uses_post_readiness_label() -> None:
    output = reconcile_client_readiness(_canonical())

    assert output["client_readiness_contract"]["maturity_label"] == "Exceptional"
    assert output["assessment"]["maturity_level"] == "Exceptional"
    assert output["assessment"]["maturity_signal"]["level"] == "Exceptional"
    assert output["assessment"]["maturity_signal"]["label"] == "Exceptional"
    evidence = output["stage_summaries"][0]["evidence"]
    assert evidence[0] == "assessment.maturity_level: Exceptional"
    assert evidence[1] == "maturity label = Exceptional"
    assert evidence[2] == "Senior engineering reviewer required"
    assert "maturity_level: Senior" not in repr(output)
    assert output["post_readiness_maturity_truth"]["canonical_label"] == "Exceptional"
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_public_text_synchronizer_changes_only_explicit_aliases() -> None:
    source = (
        "maturity_level: Senior; maturity label = Senior; "
        "Senior engineering reviewer required"
    )
    output = synchronize_explicit_maturity_text(source, "Exceptional")

    assert "maturity_level: Exceptional" in output
    assert "maturity label = Exceptional" in output
    assert "Senior engineering reviewer required" in output


def test_unscored_readiness_does_not_invent_a_maturity_label() -> None:
    canonical = _canonical()
    canonical["assessment"].pop("technical_score")
    canonical["technical_score"] = None

    output = reconcile_client_readiness(canonical)

    assert output["client_readiness_contract"]["maturity_label"] == "Not scored"
    evidence = output["stage_summaries"][0]["evidence"]
    assert evidence[0] == "assessment.maturity_level: Senior"
    assert evidence[1] == "maturity label = Senior"
    assert output["post_readiness_maturity_truth"]["status"] == "not_applied"
