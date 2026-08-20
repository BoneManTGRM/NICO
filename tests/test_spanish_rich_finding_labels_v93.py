from __future__ import annotations

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico.comprehensive_spanish_publication_preflight_v93 import (
    install_spanish_publication_preflight_v93,
)


def test_rich_finding_markdown_labels_are_localized_before_final_spanish_pass() -> None:
    result = install_spanish_publication_preflight_v93()
    assert result["rich_finding_markdown_helper_bound"] is True
    assert result["late_v88_rebind_safe"] is True

    source = "\n".join(
        [
            "## Hallazgos canónicos detallados",
            "- Finding ID: NICO-FINDING-ABC",
            "- Category / status: architecture · review_required",
            "- Exact source: nico/file.py:10",
            "- Analyzer / rule: complexity_hotspot",
            "- Evidence quality: exact commit match=True",
            "- Observed evidence: Evidencia conservada.",
            "- Interpretation: Interpretación conservada.",
            "- Technical consequence: Requiere revisión",
            "- Business consequence: Impacto conservado.",
            "- Specific correction: Corrección conservada.",
            "- Owner / effort: Arquitecto · M",
            "- Cost of inaction: No cuantificado",
            "- Residual risk: Requiere revisión",
            "- Disposition: PROPOSED · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED",
            "- Verification:",
            "- Acceptance / exit criteria:",
            "- Rollback: Reversión conservada.",
            "- Final exit criteria:",
        ]
    )

    translated = canonical._translate_presentation(source)

    for forbidden in (
        "Finding ID:",
        "Category / status:",
        "Exact source:",
        "Analyzer / rule:",
        "Evidence quality:",
        "Observed evidence:",
        "Technical consequence:",
        "Business consequence:",
        "Specific correction:",
        "Owner / effort:",
        "Cost of inaction:",
        "Residual risk:",
        "Disposition:",
        "Verification:",
        "Acceptance / exit criteria:",
        "Rollback:",
        "Final exit criteria:",
        "PROPOSED · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED",
    ):
        assert forbidden not in translated

    for required in (
        "ID del hallazgo:",
        "Categoría / estado:",
        "Fuente exacta:",
        "Analizador / regla:",
        "Calidad de la evidencia:",
        "Evidencia observada:",
        "Consecuencia técnica:",
        "Consecuencia empresarial:",
        "Corrección específica:",
        "Responsable / esfuerzo:",
        "Costo de no actuar:",
        "Riesgo residual:",
        "Disposición:",
        "Verificación:",
        "Criterios de aceptación / salida:",
        "Reversión:",
        "Criterios finales de salida:",
        "PROPUESTO · REVISIÓN DE FUENTE EXACTA Y APROBACIÓN HUMANA REQUERIDAS",
    ):
        assert required in translated

    assert "nico/file.py:10" in translated
    assert "NICO-FINDING-ABC" in translated


def test_v88_rebind_does_not_discard_rich_finding_label_localization() -> None:
    install_spanish_publication_preflight_v93()
    v88.install_comprehensive_spanish_exit_criteria_v88()

    translated = canonical._translate_presentation(
        "- Finding ID: NICO-FINDING-XYZ\n- Exact source: nico/example.py:42"
    )
    assert "- ID del hallazgo: NICO-FINDING-XYZ" in translated
    assert "- Fuente exacta: nico/example.py:42" in translated
