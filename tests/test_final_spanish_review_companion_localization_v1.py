from nico.comprehensive_current_report_truth_parity_v1 import (
    install_comprehensive_current_report_truth_parity_v1,
)


def _combined(section: dict) -> str:
    return "\n".join(
        [section["status"], section["summary"]]
        + section["evidence"]
        + section["findings"]
        + section["limitations"]
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
    combined = _combined(functional)

    # Existing truth guards may replace functional-QA status/summary before this
    # late presentation layer runs. The fields that reach this boundary must be
    # localized without weakening those upstream truth decisions.
    assert "Material confirmado findings" not in combined
    assert "verificada material findings" not in combined
    assert "History-aware secret evidence was separated" not in combined
    assert "Non-success deployment classification" not in combined
    assert "Hallazgos materiales confirmados" in combined
    assert "hallazgos materiales verificados" in combined
    assert "La evidencia de secretos con conocimiento del historial" in combined
    assert "Clasificación de despliegues no exitosos: No disponible." in combined


def test_final_spanish_leak_families_have_explicit_translations() -> None:
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    install_comprehensive_current_report_truth_parity_v1()

    assert presentation._safe_es("Review-Required Candidate Register") == (
        "Registro de candidatos que requieren revisión"
    )
    assert presentation._safe_es(
        "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification."
    ) == (
        "Reforzar los límites de arquitectura, la automatización de pruebas y publicaciones, "
        "la evidencia de QA funcional y la verificación de remediaciones."
    )
    assert presentation._safe_es(
        "Non-success deployment classification: Not available."
    ) == "Clasificación de despliegues no exitosos: No disponible."


def test_english_review_companion_copy_is_unchanged_by_localization_wrapper() -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    install_comprehensive_current_report_truth_parity_v1()
    wrapped = companion.review_sections
    previous = getattr(wrapped, "_nico_previous", None)
    assert callable(previous)

    canonical = {
        "stage_summaries": [
            {
                "stage_id": "functional_qa",
                "status": "Review-Required Candidate Register",
                "summary": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
                "evidence": ["Material confirmado findings: 0."],
            }
        ]
    }

    expected = previous(canonical, spanish=False)
    actual = wrapped(canonical, spanish=False)
    assert actual == expected
