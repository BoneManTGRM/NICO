from pathlib import Path

from nico.comprehensive_current_report_truth_parity_v1 import _ES_PHRASES
from nico.comprehensive_spanish_current_copy_worker_v98 import (
    install_comprehensive_spanish_current_copy_worker_v98,
    localize_current_report_copy_v98,
)
from nico.comprehensive_spanish_publication_preflight_v93 import (
    inspect_spanish_canonical_publication_preflight,
)


WORKER_BOOTSTRAP = Path("nico/api/final_report_worker_bootstrap.py").read_text(
    encoding="utf-8"
)
PARENT_BOOTSTRAP = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
    encoding="utf-8"
)


def test_v98_localizes_every_current_report_leak_contract() -> None:
    for source, target in _ES_PHRASES.items():
        localized = localize_current_report_copy_v98(source)
        assert source not in localized or source == target
        assert target in localized


def test_v98_closes_live_gitlab_anonymous_capability_preflight() -> None:
    install_comprehensive_spanish_current_copy_worker_v98()

    deployment = "deployments evidence is unavailable without read-only authentication"
    environment = "environments evidence is unavailable without read-only authentication"
    provider_summary = (
        "Exact-revision provider repository, dependency, architecture, workflow, activity, "
        "and complexity evidence were attached through the canonical provider-neutral path."
    )
    canonical_report = {
        "report_language": "es-MX",
        "identity": {"report_language": "es-MX"},
        "assessment": {
            "unavailable_data_notes": [deployment, environment],
        },
        "stage_summaries": [
            {
                "unavailable": [deployment, environment],
                "summary": provider_summary,
            }
        ],
    }
    before = repr(canonical_report)

    manifest = inspect_spanish_canonical_publication_preflight(canonical_report)

    assert manifest["status"] == "complete"
    assert manifest["failure_count"] == 0
    assert manifest["checked_presentation_values"] == 5
    assert repr(canonical_report) == before

    assert localize_current_report_copy_v98(deployment) == (
        "La evidencia de despliegues no está disponible sin autenticación de solo lectura."
    )
    assert localize_current_report_copy_v98(environment) == (
        "La evidencia de entornos no está disponible sin autenticación de solo lectura."
    )
    localized_summary = localize_current_report_copy_v98(provider_summary)
    assert "Exact-revision provider repository" not in localized_summary
    assert "revisión exacta" in localized_summary
    assert "ruta canónica neutral al proveedor" in localized_summary


def test_v98_localizes_dynamic_current_report_fragments_without_touching_unknown_copy() -> None:
    source = (
        "Review-Required Candidate Register; Material confirmado findings: 0; "
        "verificada material findings: 2; Strengthen architecture boundaries, "
        "test/release automation, functional QA evidence, and remediation verification."
    )
    localized = localize_current_report_copy_v98(source)

    assert "Review-Required Candidate Register" not in localized
    assert "Material confirmado findings" not in localized
    assert "verificada material findings" not in localized
    assert "Strengthen architecture boundaries" not in localized
    assert "Registro de candidatos que requieren revisión" in localized
    assert "Hallazgos materiales confirmados: 0" in localized
    assert "hallazgos materiales verificados: 2" in localized
    assert "Reforzar los límites de arquitectura" in localized

    unknown = "Brand-new unregistered report prose must still fail closed upstream."
    assert localize_current_report_copy_v98(unknown) == unknown


def test_v98_localizes_bounded_workflow_job_evidence_without_value_drift() -> None:
    source = (
        "Workflow jobs: 9 successful of 9 observed (100%); bounded observed job "
        "sample; count basis=retained rate and denominator."
    )

    localized = localize_current_report_copy_v98(source)

    assert localized == (
        "Trabajos de flujo de trabajo: 9 exitosos de 9 observados (100%); "
        "muestra acotada de trabajos observados; base del conteo=tasa y "
        "denominador conservados."
    )
    assert "Workflow jobs" not in localized
    assert "bounded observed job sample" not in localized
    assert "retained rate and denominator" not in localized

    install_comprehensive_spanish_current_copy_worker_v98()
    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    assert canonical._translate_presentation_field(source, "evidence") == localized


def test_v98_binds_the_real_spanish_translation_surfaces() -> None:
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    state = install_comprehensive_spanish_current_copy_worker_v98()
    assert state["status"] == "installed"
    assert state["bound"] is True
    assert state["current_report_copy_contract_bound"] is True
    assert state["unknown_prose_still_delegates_fail_closed"] is True

    dynamic = canonical._translate_presentation(
        "Material confirmado findings: 0. Strengthen architecture boundaries, "
        "test/release automation, functional QA evidence, and remediation verification."
    )
    assert "Material confirmado findings" not in dynamic
    assert "Strengthen architecture boundaries" not in dynamic
    assert "Hallazgos materiales confirmados" in dynamic
    assert "Reforzar los límites de arquitectura" in dynamic

    status = presentation._safe_es("Review-Required Candidate Register")
    assert status == "Registro de candidatos que requieren revisión"


def test_parent_and_isolated_worker_bind_v98_before_v94_cache() -> None:
    binder = "install_comprehensive_spanish_current_copy_worker_v98()"
    cache = "install_comprehensive_spanish_final_report_runtime_cache_v94()"

    assert binder in WORKER_BOOTSTRAP
    assert cache in WORKER_BOOTSTRAP
    assert WORKER_BOOTSTRAP.index(binder) < WORKER_BOOTSTRAP.index(cache)
    assert '"spanish_current_report_copy_contract_bound": True' in WORKER_BOOTSTRAP

    assert binder in PARENT_BOOTSTRAP
    assert cache in PARENT_BOOTSTRAP
    assert PARENT_BOOTSTRAP.index(binder) < PARENT_BOOTSTRAP.index(cache)


def test_v98_does_not_change_english_report_data_directly() -> None:
    # The v98 helper is invoked only from Spanish translation surfaces. It never edits
    # canonical data or the English renderer; the source object itself stays untouched.
    source = "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification."
    canonical_value = source
    _ = localize_current_report_copy_v98(source)
    assert canonical_value == source


def test_v98_localizes_late_deployment_tree_scanner_and_candidate_grammars() -> None:
    source = "\n".join(
        (
            "Non-success or unresolved deployment observations: 3.",
            "Outcome classification breakdown: No disponible.",
            "Top-level entries[0]: Dockerfile",
            "pip-audit: completed; commit exacto=sí; artefacto=conservado; conteo de hallazgos materiales confirmados=0; carga de hallazgos sin procesar incluida=no.",
            "Dependency: raw=21; confirmed_material=0; review_required=21; excluded_test_only=0; approved_or_nonblocking=0.",
            "- Static · B105 · tool=bandit; package=requests; installed=2.31.0; fixed=2.32.0; location=nico/admin_security.py; disposition=review_required · El triaje técnico permanece separado.",
        )
    )

    localized = localize_current_report_copy_v98(source)

    assert "Observaciones de despliegues no exitosos o no resueltos: 3." in localized
    assert "Desglose de la clasificación de resultados: No disponible." in localized
    assert "Elementos de nivel superior[0]: Dockerfile" in localized
    assert "pip-audit: ejecución completada; commit exacto=sí" in localized
    assert "Dependencias: brutos=21; materiales confirmados=0; requieren revisión=21" in localized
    assert "Análisis estático · B105 · herramienta=bandit" in localized
    assert "paquete=requests" in localized
    assert "versión instalada=2.31.0" in localized
    assert "versión corregida=2.32.0" in localized
    assert "ubicación=nico/admin_security.py" in localized
    assert "disposición=revisión requerida" in localized

    for leaked in (
        "Non-success or unresolved deployment observations",
        "Outcome classification breakdown",
        "Top-level entries",
        ": completed; commit exacto=",
        "Dependency: raw=",
        "tool=",
        "location=",
        "disposition=review_required",
    ):
        assert leaked not in localized


def test_v98_localizes_final_scanner_summary_and_priority_reason_before_pdf_layout() -> None:
    scanner = (
        "pip-audit: completed; exact commit=yes; artifact=retained; "
        "confirmed material finding count=0; raw finding payload embedded=no."
    )
    priority = (
        "top_technical_priorities[0].reason: Snapshot-bound source footprint and "
        "measured complexity evidence were evaluated without score override."
    )

    localized = localize_current_report_copy_v98(f"{scanner}\n{priority}")

    assert "pip-audit: ejecución completada; commit exacto=sí" in localized
    assert "artefacto=conservado" in localized
    assert "conteo de hallazgos materiales confirmados=0" in localized
    assert "carga de hallazgos sin procesar incluida=no" in localized
    assert "Se evaluaron la huella del código fuente vinculada a la instantánea" in localized
    assert "completed; exact commit=" not in localized
    assert "Snapshot-bound source footprint" not in localized


def test_v98_localizes_authorized_human_disposition_score_effect() -> None:
    source = "Score effect: assurance-only until triaged."

    localized = localize_current_report_copy_v98(source)

    assert source not in localized
    assert localized == (
        "Efecto en la puntuación: solo aseguramiento mientras la disposición humana "
        "autorizada siga pendiente; el estado del triaje técnico de NICO se informa "
        "por separado."
    )
