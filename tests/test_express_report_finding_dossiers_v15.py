from nico.express_report_finding_dossiers_v15 import build_finding_dossiers, report_labels


def _fixture() -> dict:
    return {
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "evidence": ["Semgrep exact-snapshot artifact", "Bandit execution log"],
                "findings": ["Bandit failed during exact-snapshot execution.", "Semgrep findings require review."],
            }
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Bandit failed during exact-snapshot execution.",
                    "severity": "high",
                    "confidence": "high",
                    "business_impact": "Static-analysis assurance is incomplete.",
                    "recommended_action": "Repair the worker execution path and rerun Bandit against the immutable snapshot.",
                    "owner": "Platform engineering",
                    "effort": "2-4 hours",
                    "verification": "Retain parseable Bandit output and rerun focused plus full tests.",
                    "rollback": "Restore the previous worker image if the scanner bootstrap regresses.",
                    "residual_risk": "Python-specific findings remain unknown until execution succeeds.",
                }
            ]
        },
    }


def test_each_finding_has_a_stable_decision_ready_dossier() -> None:
    dossiers = build_finding_dossiers(_fixture())
    assert len(dossiers) == 2
    first = dossiers[0]
    assert first.finding_id.startswith("FND-")
    assert first.section_id == "static_analysis"
    assert first.evidence
    assert first.business_impact != "Not provided"
    assert first.repair_specification != "Not provided"
    assert first.owner != "Not provided"
    assert first.effort != "Not provided"
    assert first.verification != "Not provided"
    assert first.rollback != "Not provided"
    assert first.residual_risk != "Not provided"


def test_finding_ids_are_deterministic_and_duplicates_are_suppressed() -> None:
    fixture = _fixture()
    fixture["sections"][0]["findings"].append("Bandit failed during exact-snapshot execution.")
    first = build_finding_dossiers(fixture)
    second = build_finding_dossiers(fixture)
    assert len(first) == 2
    assert [item.finding_id for item in first] == [item.finding_id for item in second]


def test_english_and_spanish_report_catalogs_have_exact_structural_parity() -> None:
    english = report_labels("en-US")
    spanish = report_labels("es-MX")
    assert set(english) == set(spanish)
    assert english["finding_dossier"] == "Finding Dossier"
    assert spanish["finding_dossier"] == "Expediente del Hallazgo"
    assert english["human_review"] == "Human review required"
    assert spanish["human_review"] == "Se requiere revisión humana"
