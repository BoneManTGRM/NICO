from nico.comprehensive_current_report_truth_parity_v1 import (
    install_comprehensive_current_report_truth_parity_v1,
)


def test_late_review_companion_dynamic_copy_is_localized() -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    install_comprehensive_current_report_truth_parity_v1()
    canonical = {
        "identity": {"report_language": "es-MX"},
        "stage_summaries": [
            {
                "stage_id": "functional_qa",
                "status": "Review-Required Candidate Register",
                "summary": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
                "evidence": [
                    "Material confirmado findings: 0.",
                    "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.",
                ],
                "findings": ["verificada material findings: 0."],
                "limitations": ["Non-success deployment classification: Not available."],
            }
        ],
    }

    sections = companion.review_sections(canonical, spanish=True)
    functional = next(item for item in sections if item["id"] == "functional_qa")
    combined = "\n".join(
        [functional["status"], functional["summary"]]
        + functional["evidence"]
        + functional["findings"]
        + functional["limitations"]
    )
    assert "Review-Required Candidate Register" not in combined
    assert "Material confirmado findings" not in combined
    assert "verificada material findings" not in combined
    assert "Strengthen architecture boundaries" not in combined
    assert "Non-success deployment classification" not in combined
    assert "Registro de candidatos que requieren revisión" in combined
    assert "Hallazgos materiales confirmados" in combined
    assert "Clasificación de despliegues no exitosos: No disponible." in combined


def test_english_review_companion_copy_is_unchanged() -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    install_comprehensive_current_report_truth_parity_v1()
    canonical = {
        "stage_summaries": [
            {
                "stage_id": "functional_qa",
                "status": "Review-Required Candidate Register",
                "summary": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
            }
        ]
    }
    sections = companion.review_sections(canonical, spanish=False)
    functional = next(item for item in sections if item["id"] == "functional_qa")
    assert functional["status"] == "Review-Required Candidate Register"
    assert functional["summary"].startswith("Strengthen architecture boundaries")
