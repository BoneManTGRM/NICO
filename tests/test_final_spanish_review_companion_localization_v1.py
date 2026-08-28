import io

from pypdf import PdfReader

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


def _intrinsic_review_sections():
    from nico import comprehensive_client_review_companion_v2 as companion

    current = companion.review_sections
    while callable(getattr(current, "_nico_previous", None)):
        current = current._nico_previous
    return current


def test_review_companion_intrinsically_localizes_production_leak_families() -> None:
    review_sections = _intrinsic_review_sections()
    canonical = {
        "identity": {"report_language": "es-MX"},
        "stage_summaries": [
            {
                "stage_id": "functional_qa",
                "status": "Review-Required Candidate Register",
                "summary": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
                "evidence": [
                    "Material confirmado findings: 0.",
                    "verificada material findings: 0.",
                    "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.",
                    "Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.",
                    "Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.",
                    "Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.",
                ],
                "limitations": [
                    "Non-success deployment classification: Not available.",
                    "Job success rate: Not available.",
                ],
            }
        ],
    }

    sections = review_sections(canonical, spanish=True)
    functional = next(item for item in sections if item["id"] == "functional_qa")
    combined = _combined(functional)

    for marker in (
        "Review-Required Candidate Register",
        "Material confirmado findings",
        "verificada material findings",
        "Strengthen architecture boundaries",
        "History-aware secret evidence was separated",
        "Sustainable delivery capacity is derived",
        "Exact-commit executable source signals were analyzed",
        "Authoritative manifests and contextual dependency evidence were reconciled",
        "Non-success deployment classification",
        "Job success rate",
    ):
        assert marker not in combined

    # Functional-QA truth guards may replace status/summary before this late
    # companion boundary runs. Prove localization for the dynamic fields that
    # actually survive to this boundary without weakening those truth guards.
    assert "Hallazgos materiales confirmados" in combined
    assert "hallazgos materiales verificados" in combined
    assert "La evidencia de secretos con conocimiento del historial" in combined
    assert "La capacidad de entrega sostenible" in combined
    assert "Se analizaron las señales ejecutables del código fuente del commit exacto" in combined
    assert "Los manifiestos autoritativos y la evidencia contextual de dependencias" in combined
    assert "Clasificación de despliegues no exitosos: No disponible." in combined
    assert "Tasa de éxito de trabajos: No disponible." in combined


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


def _authored_finding_register() -> dict:
    return {
        "summary": {
            "decision_finding_count": 1,
            "exact_source_code_finding_count": 1,
            "operational_or_context_finding_count": 0,
        },
        "code_findings": [
            {
                "priority": "P2",
                "finding_id": "RISK-P1-001",
                "title": "Reduce complexity in page.tsx",
                "location": "apps/web/app/page.tsx:100",
                "observed_evidence": (
                    "The canonical finding was retained against the assessed "
                    "immutable commit."
                ),
                "business_impact": "Regression risk is concentrated.",
                "recommended_correction": (
                    "Extract state transitions, data loading, and side-effect "
                    "orchestration from `the identified unit` into typed hooks or "
                    "services; split independent rendering branches into bounded "
                    "child components; add characterization and Playwright coverage; "
                    "then enforce cyclomatic complexity at or below 30 for the "
                    "durable source anchor."
                ),
                "verification": [
                    "The exact-SHA rerun no longer reports this condition at "
                    "apps/web/app/page.tsx:100.",
                    "Targeted tests and the repository's full required-check suite "
                    "pass on the remediation commit.",
                ],
            }
        ],
        "operational_findings": [],
    }


def test_active_spanish_review_and_register_renderers_localize_authored_copy() -> None:
    from nico.comprehensive_client_ready_projection_v1 import (
        compact_finding_register_markdown,
        render_compact_finding_register_pdf,
    )
    from nico.comprehensive_client_review_companion_v7 import (
        render_paired_substantive_review_pdf,
    )
    from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status

    register = _authored_finding_register()
    canonical = {
        "identity": {"report_language": "es-MX"},
        "assessment": {
            "canonical_scanner_finding_register": {
                "totals": {"material": 0, "review_required": 0}
            }
        },
        "client_finding_remediation_register": register,
    }

    review_pdf = render_paired_substantive_review_pdf(canonical, spanish=True)
    sanitized_review_pdf = sanitize_client_pdf_status(review_pdf)
    register_pdf = render_compact_finding_register_pdf(register, spanish=True)
    review_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(review_pdf)).pages
    )
    register_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(register_pdf)).pages
    )
    sanitized_reader = PdfReader(io.BytesIO(sanitized_review_pdf))
    assert len(sanitized_reader.pages) == 4
    assert "QA funcional" in "\n".join(
        page.extract_text() or "" for page in sanitized_reader.pages
    )
    markdown = compact_finding_register_markdown(register, spanish=True)
    combined = "\n".join((review_text, register_text, markdown))

    for marker in (
        "NICO | Comprehensive client review | automated draft",
        "Review page ",
        "Human context or additional evidence",
        "Named people, rates, contract structure",
        "Decision findings:",
        "Exact-source findings:",
        "Confirmed material scanner findings:",
        "Review-required scanner candidates:",
        "Reduce complexity in",
        "The canonical finding was retained",
        "Regression risk is concentrated",
        "Extract state transitions",
        "The exact-SHA rerun",
        "Targeted tests and the repository's full required-check suite",
        "NICO · compact finding register · automated draft",
        "Finding ID",
        "Exact source",
        "Finding / disposition",
    ):
        assert marker not in combined

    for marker in (
        "NICO | revisión integral del cliente | borrador automatizado",
        "Página de revisión 1 de 4 | Secciones 1-2 de 8",
        "Se requiere contexto humano o evidencia adicional antes de aceptar esta sección.",
        "Hallazgos de decisión: 1",
        "Hallazgos con ubicación exacta: 1",
        "Reducir la complejidad en page.tsx",
        "El hallazgo canónico se conservó contra el commit inmutable evaluado.",
        "El riesgo de regresión está concentrado.",
        "Extraer las transiciones de estado",
        "La nueva ejecución sobre el SHA exacto",
        "Las pruebas dirigidas y el conjunto completo de verificaciones requeridas",
        "NICO · registro compacto de hallazgos · borrador automatizado",
        "ID del hallazgo",
        "Fuente exacta",
        "Hallazgo / disposición",
    ):
        assert marker in combined

    # Deliberate allowlist: source identity and tool/format literals are not prose.
    for literal in (
        "RISK-P1-001",
        "apps/web/app/page.tsx:100",
        "page.tsx",
        "Playwright",
        "JSON",
        "CSV",
        "SHA",
    ):
        assert literal in combined
