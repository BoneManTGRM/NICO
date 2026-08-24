import pytest

from nico.comprehensive_current_report_truth_parity_v1 import (
    install_comprehensive_current_report_truth_parity_v1,
    strict_spanish_presentation_v1,
)
from nico.comprehensive_report_semantic_manifest_v1 import (
    CANONICAL_TOC_SECTION_IDS,
    CANONICAL_TOC_TITLES,
    REPORT_SECTION_MANIFEST,
    SECTION_TITLE_ES_BY_EN,
    assert_manifest_integrity,
)
from nico.comprehensive_spanish_current_copy_worker_v98 import (
    localize_current_report_copy_v98,
)


def test_canonical_semantic_manifest_is_complete_unique_and_ordered() -> None:
    assert_manifest_integrity()
    assert REPORT_SECTION_MANIFEST
    assert len(CANONICAL_TOC_SECTION_IDS) == len(set(CANONICAL_TOC_SECTION_IDS))
    assert len(CANONICAL_TOC_TITLES) == len(set(CANONICAL_TOC_TITLES))
    required = {
        "section_id",
        "title_en",
        "title_es",
        "purpose",
        "inclusion_criteria",
        "client_visible",
        "toc_participation",
        "review_package_participation",
        "required",
        "artifact_owner",
    }
    for section in REPORT_SECTION_MANIFEST:
        assert required <= set(section)
        assert section["title_en"]
        assert section["title_es"]


def test_runtime_english_and_spanish_navigation_share_one_manifest() -> None:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import comprehensive_spanish_presentation_parity_v1 as spanish

    state = install_comprehensive_current_report_truth_parity_v1()

    assert state["canonical_semantic_report_manifest"] is True
    assert cleanup._TOC_TITLES == CANONICAL_TOC_TITLES
    assert tuple(spanish._TITLE_MAP) == tuple(SECTION_TITLE_ES_BY_EN)
    assert spanish._TITLE_MAP == SECTION_TITLE_ES_BY_EN


def test_repository_evidence_and_evidence_reconciliation_are_distinct_canonical_sections() -> None:
    repository_index = CANONICAL_TOC_TITLES.index("Repository and Delivery Evidence")
    reconciliation_index = CANONICAL_TOC_TITLES.index("Evidence Reconciliation and Scoring")

    assert reconciliation_index == repository_index + 1
    assert CANONICAL_TOC_SECTION_IDS[repository_index] == "repository_delivery_evidence"
    assert CANONICAL_TOC_SECTION_IDS[reconciliation_index] == "evidence_reconciliation_scoring"
    assert SECTION_TITLE_ES_BY_EN["Repository and Delivery Evidence"] == (
        "Evidencia del repositorio y de entrega"
    )
    assert SECTION_TITLE_ES_BY_EN["Evidence Reconciliation and Scoring"] == (
        "Conciliación y puntuación de evidencia"
    )


def test_canonical_manifest_preserves_english_and_covers_spanish_navigation_titles() -> None:
    expected = {
        "Code audit": "Auditoría de código",
        "Executive Risk Register and Decision Briefing": (
            "Registro ejecutivo de riesgos y resumen para decisiones"
        ),
        "Platform Parity": "Paridad de plataformas",
        "Historical Trends and Change Failure": "Tendencias históricas y fallos de cambio",
        "Stakeholder and Business Alignment": "Alineación comercial y de partes interesadas",
        "Risk Reduction and Executive Briefing": "Reducción de riesgo y resumen ejecutivo",
        "Six-Month Roadmap": "Hoja de ruta de seis meses",
        "Staffing, Sequencing, and Cost": "Personal, secuencia y costo",
    }
    for english, spanish in expected.items():
        assert english in CANONICAL_TOC_TITLES
        assert SECTION_TITLE_ES_BY_EN[english] == spanish


def test_provider_ci_generator_family_localizes_without_changing_dynamic_values() -> None:
    source = (
        "Workflow files at assessed commit: 17. "
        "Workflow configuration exact-SHA match: True. "
        "Explicit permissions control: passed. "
        "Provider-neutral immutable CI objective coverage: 100%. "
        "CI control assurance incomplete; no pass/fail claim was made for: explicit_permissions_present, concurrency."
    )
    localized = localize_current_report_copy_v98(source)

    assert "Workflow files at assessed commit" not in localized
    assert "Workflow configuration exact-SHA match" not in localized
    assert "Explicit permissions control" not in localized
    assert "Provider-neutral immutable CI objective coverage" not in localized
    assert "no pass/fail claim was made for" not in localized
    assert "Archivos de flujo de trabajo en el commit evaluado: 17." in localized
    assert "Coincidencia exacta de SHA de la configuración del flujo de trabajo: sí." in localized
    assert "Control de permisos explícitos: aprobado." in localized
    assert "Cobertura de objetivos inmutables de CI independiente del proveedor: 100%." in localized
    assert "explicit_permissions_present, concurrency" in localized


def test_candidate_volume_score_effect_sentence_is_fully_spanish() -> None:
    for score_label in ("Evidence-Adjusted", "Ajuste por evidencia"):
        source = (
            "Candidate volume and reviewer workload are operational review metrics and have no "
            f"numeric technical-maturity or {score_label} score effect."
        )
        localized = localize_current_report_copy_v98(source)
        assert "Candidate volume and reviewer workload" not in localized
        assert "technical-maturity" not in localized
        assert "score effect" not in localized
        assert "El volumen de candidatos y la carga de trabajo del revisor" in localized
        assert "Ajuste por evidencia" in localized


def test_current_copy_preprojection_does_not_create_a_broad_english_allowlist() -> None:
    unknown = "Brand-new unregistered renderer-owned sentence must fail closed."
    assert localize_current_report_copy_v98(unknown) == unknown


def test_strict_late_presentation_boundary_rejects_unknown_renderer_owned_english() -> None:
    with pytest.raises(ValueError, match="Spanish|spanish|translation|presentation"):
        strict_spanish_presentation_v1(
            "Brand-new unregistered renderer-owned sentence must fail closed."
        )


def test_strict_late_presentation_boundary_preserves_protected_source_atom() -> None:
    technical_atom = "nico/provider_control_objective_parity_v1.py:321"
    assert strict_spanish_presentation_v1(technical_atom) == technical_atom


def test_late_spanish_review_companion_localizes_provider_ci_copy(monkeypatch) -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    def fixture_sections(canonical, *, spanish):
        return [
            {
                "id": "fixture",
                "title": "fixture",
                "status": "Review-Required Candidate Register",
                "summary": (
                    "Candidate volume and reviewer workload are operational review metrics and have no "
                    "numeric technical-maturity or Evidence-Adjusted score effect."
                ),
                "evidence": [
                    "Explicit permissions control: passed.",
                    "Provider-neutral immutable CI objective coverage: 100%.",
                ],
                "findings": [],
                "limitations": [],
            }
        ]

    monkeypatch.setattr(companion, "review_sections", fixture_sections)
    install_comprehensive_current_report_truth_parity_v1()
    section = companion.review_sections({}, spanish=True)[0]
    combined = "\n".join(
        [section["status"], section["summary"]]
        + section["evidence"]
        + section["findings"]
        + section["limitations"]
    )

    assert "Review-Required Candidate Register" not in combined
    assert "Candidate volume and reviewer workload" not in combined
    assert "Explicit permissions control" not in combined
    assert "Provider-neutral immutable CI objective coverage" not in combined
    assert "Registro de candidatos que requieren revisión" in combined
    assert "El volumen de candidatos y la carga de trabajo del revisor" in combined
    assert "Control de permisos explícitos: aprobado." in combined
    assert "Cobertura de objetivos inmutables de CI independiente del proveedor: 100%." in combined


def test_late_spanish_review_companion_rejects_unknown_renderer_owned_english(monkeypatch) -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    def fixture_sections(canonical, *, spanish):
        return [
            {
                "id": "fixture",
                "title": "fixture",
                "status": "complete",
                "summary": "Brand-new unregistered renderer-owned sentence must fail closed.",
                "evidence": [],
                "findings": [],
                "limitations": [],
            }
        ]

    monkeypatch.setattr(companion, "review_sections", fixture_sections)
    install_comprehensive_current_report_truth_parity_v1()
    with pytest.raises(ValueError, match="Spanish|spanish|translation|presentation"):
        companion.review_sections({}, spanish=True)


def test_protected_technical_source_atom_remains_exact_in_spanish_review_companion(monkeypatch) -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    technical_atom = "nico/provider_control_objective_parity_v1.py:321"

    def fixture_sections(canonical, *, spanish):
        return [
            {
                "id": "fixture",
                "title": "fixture",
                "status": "Review-Required Candidate Register",
                "summary": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
                "evidence": [technical_atom],
                "findings": [],
                "limitations": [],
            }
        ]

    monkeypatch.setattr(companion, "review_sections", fixture_sections)
    install_comprehensive_current_report_truth_parity_v1()
    section = companion.review_sections({}, spanish=True)[0]
    assert technical_atom in section["evidence"]


def test_english_review_companion_is_unchanged_by_strict_spanish_wrapper(monkeypatch) -> None:
    from nico import comprehensive_client_review_companion_v2 as companion

    expected = [
        {
            "id": "fixture",
            "title": "fixture",
            "status": "complete",
            "summary": "English output remains English.",
            "evidence": ["Explicit permissions control: passed."],
            "findings": [],
            "limitations": [],
        }
    ]

    def fixture_sections(canonical, *, spanish):
        return [dict(item) for item in expected]

    monkeypatch.setattr(companion, "review_sections", fixture_sections)
    install_comprehensive_current_report_truth_parity_v1()
    assert companion.review_sections({}, spanish=False) == expected
