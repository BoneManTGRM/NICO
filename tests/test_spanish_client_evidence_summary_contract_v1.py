from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_client_ready_projection_v1 as client_projection
from nico.candidate_phase1_report_workload_pdf_v1 import (
    render_phase1_evidence_review_gate_pdf,
)
from nico.spanish_client_evidence_summary_contract_v1 import (
    client_evidence_summary_has_five_fields,
)


VALUES = (
    "Cody Jenkins",
    "NICO Audit",
    "Cody — Repository owner / project lead",
    "Public GitHub repository via HTTPS/API — read-only access",
    (
        "BoneManTGRM/NICO — entire repository, current main branch, including "
        "source code, configuration, CI/CD workflows, dependency manifests, "
        "documentation, and repository metadata. Read-only technical and "
        "security assessment."
    ),
)

LOCALE_CONTRACTS = (
    (
        "es-MX",
        "Resumen de evidencia del cliente",
        (
            "Nombre del cliente",
            "Nombre del proyecto",
            "Contacto técnico principal",
            "Método de acceso",
            "Alcance autorizado",
        ),
        "El triaje técnico y la disposición humana están separados",
    ),
    (
        "en",
        "Client Evidence Summary",
        (
            "Client name",
            "Project name",
            "Primary technical contact",
            "Access method",
            "Authorized scope",
        ),
        "Technical triage and human disposition are separate",
    ),
)

APPROVAL_WARNINGS = {
    "es-MX": (
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
        "ENTREGA AL CLIENTE BLOQUEADA"
    ),
    "en": (
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    ),
}
SUMMARY_PREAMBLES = {
    "es-MX": f"{APPROVAL_WARNINGS['es-MX']} Campo Valor",
    "en": f"{APPROVAL_WARNINGS['en']} Field Value",
}


@pytest.mark.parametrize(
    ("language", "summary_heading", "labels", "following_heading"),
    LOCALE_CONTRACTS,
)
def test_current_workload_layout_consolidates_all_five_fields(
    language: str,
    summary_heading: str,
    labels: tuple[str, ...],
    following_heading: str,
) -> None:
    rows = " ".join(
        f"{label}: {value}" for label, value in zip(labels, VALUES, strict=True)
    )
    rendered = (
        f"Cover {summary_heading} {SUMMARY_PREAMBLES[language]} "
        f"{rows} {following_heading} Later section"
    )

    assert client_evidence_summary_has_five_fields(
        rendered,
        report_language=language,
        expected_values=VALUES,
    )


@pytest.mark.parametrize(
    ("language", "summary_heading", "labels", "following_heading"),
    (
        (
            "es-MX",
            "Resumen de evidencia del cliente",
            (
                "Nombre del cliente",
                "Nombre del proyecto",
                "Contacto técnico principal",
                "Método de acceso",
                "Alcance autorizado",
            ),
            "Separación de ejecución y disposición",
        ),
        (
            "en",
            "Client Evidence Summary",
            (
                "Client name",
                "Project name",
                "Primary technical contact",
                "Access method",
                "Authorized scope",
            ),
            "Execution and disposition are separate",
        ),
    ),
)
def test_direct_projection_layout_remains_supported(
    language: str,
    summary_heading: str,
    labels: tuple[str, ...],
    following_heading: str,
) -> None:
    rows = " ".join(
        f"{label}: {value}" for label, value in zip(labels, VALUES, strict=True)
    )

    assert client_evidence_summary_has_five_fields(
        (
            f"{summary_heading} {APPROVAL_WARNINGS[language]} "
            f"{rows} {following_heading}"
        ),
        report_language=language,
        expected_values=VALUES,
    )


def test_nearest_boundary_prevents_values_elsewhere_from_satisfying_summary() -> None:
    labels = (
        "Nombre del cliente",
        "Nombre del proyecto",
        "Contacto técnico principal",
        "Método de acceso",
        "Alcance autorizado",
    )
    rows = " ".join(
        f"{label}: {value}" for label, value in zip(labels, VALUES, strict=True)
    )
    rendered = (
        "Resumen de evidencia del cliente "
        f"{SUMMARY_PREAMBLES['es-MX']} Nombre del cliente: Cody Jenkins "
        "Separación de ejecución y disposición "
        f"{rows} El triaje técnico y la disposición humana están separados"
    )

    assert not client_evidence_summary_has_five_fields(
        rendered,
        report_language="es-MX",
        expected_values=VALUES,
    )


@pytest.mark.parametrize(
    ("language", "summary_heading", "labels", "following_heading"),
    LOCALE_CONTRACTS,
)
def test_repeated_heading_cannot_merge_fields_across_summary_sections(
    language: str,
    summary_heading: str,
    labels: tuple[str, ...],
    following_heading: str,
) -> None:
    first_rows = " ".join(
        f"{label}: {value}"
        for label, value in zip(labels[:3], VALUES[:3], strict=True)
    )
    second_rows = " ".join(
        f"{label}: {value}"
        for label, value in zip(labels[3:], VALUES[3:], strict=True)
    )
    rendered = (
        f"{summary_heading} {SUMMARY_PREAMBLES[language]} {first_rows} "
        f"{summary_heading} {SUMMARY_PREAMBLES[language]} "
        f"{second_rows} {following_heading}"
    )

    assert not client_evidence_summary_has_five_fields(
        rendered,
        report_language=language,
        expected_values=VALUES,
    )


@pytest.mark.parametrize(
    ("language", "summary_heading", "labels", "following_heading"),
    LOCALE_CONTRACTS,
)
def test_each_value_must_be_bound_to_its_corresponding_label(
    language: str,
    summary_heading: str,
    labels: tuple[str, ...],
    following_heading: str,
) -> None:
    labels_then_values = " ".join((*labels, *VALUES))
    swapped_rows = " ".join(
        f"{label}: {value}"
        for label, value in zip(labels, reversed(VALUES), strict=True)
    )

    for body in (labels_then_values, swapped_rows):
        assert not client_evidence_summary_has_five_fields(
            (
                f"{summary_heading} {SUMMARY_PREAMBLES[language]} "
                f"{body} {following_heading}"
            ),
            report_language=language,
            expected_values=VALUES,
        )


def test_boundary_words_inside_a_value_fail_closed() -> None:
    labels = tuple(LOCALE_CONTRACTS[1][2])
    boundary = str(LOCALE_CONTRACTS[1][3])
    values = (
        *VALUES[:3],
        f"Approved note: {boundary}; read-only access",
        VALUES[4],
    )
    rows = " ".join(
        f"{label}: {value}" for label, value in zip(labels, values, strict=True)
    )

    assert not client_evidence_summary_has_five_fields(
        (
            f"Client Evidence Summary {SUMMARY_PREAMBLES['en']} "
            f"{rows} {boundary}"
        ),
        report_language="en",
        expected_values=values,
    )


@pytest.mark.parametrize(
    ("language", "summary_heading", "labels", "following_heading"),
    LOCALE_CONTRACTS,
)
def test_canonical_summary_cannot_span_unrelated_pages_to_workload_boundary(
    language: str,
    summary_heading: str,
    labels: tuple[str, ...],
    following_heading: str,
) -> None:
    rows = " ".join(
        f"{label}: {value}" for label, value in zip(labels, VALUES, strict=True)
    )
    rendered_without_workload_summary = (
        f"Table of contents {summary_heading} Other entries "
        f"{summary_heading} Stage ID client_evidence_summary {rows} "
        f"{'unrelated finding content ' * 200} {following_heading}"
    )

    assert not client_evidence_summary_has_five_fields(
        rendered_without_workload_summary,
        report_language=language,
        expected_values=VALUES,
    )


@pytest.mark.parametrize(("language", "spanish"), (("es-MX", True), ("en", False)))
def test_current_phase1_pdf_renderer_satisfies_summary_contract(
    language: str,
    spanish: bool,
) -> None:
    canonical = {
        "identity": {
            "customer_name": VALUES[0],
            "project_name": VALUES[1],
            "primary_technical_contact": VALUES[2],
            "access_method": VALUES[3],
            "authorized_scope": VALUES[4],
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_renderer_contract",
        },
        "assessment": {},
        "scanner_execution_records": [],
    }
    pdf = render_phase1_evidence_review_gate_pdf(
        canonical,
        {"summary": {"exact_source_code_finding_count": 0}},
        spanish=spanish,
    )
    rendered = "\n".join(
        str(page.extract_text() or "")
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert client_evidence_summary_has_five_fields(
        rendered,
        report_language=language,
        expected_values=VALUES,
    )


@pytest.mark.parametrize(("language", "spanish"), (("es-MX", True), ("en", False)))
def test_unwrapped_direct_pdf_renderer_satisfies_summary_contract(
    language: str,
    spanish: bool,
) -> None:
    canonical = {
        "identity": {
            "customer_name": VALUES[0],
            "project_name": VALUES[1],
            "primary_technical_contact": VALUES[2],
            "access_method": VALUES[3],
            "authorized_scope": VALUES[4],
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "run_id": "comprun_direct_renderer_contract",
        },
        "assessment": {},
        "scanner_execution_records": [],
    }
    base_renderer = client_projection.render_evidence_review_gate_pdf
    while getattr(base_renderer, "_nico_previous", None) is not None:
        base_renderer = base_renderer._nico_previous
    pdf = base_renderer(
        canonical,
        {"summary": {"exact_source_code_finding_count": 0}},
        spanish=spanish,
    )
    rendered = "\n".join(
        str(page.extract_text() or "")
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert client_evidence_summary_has_five_fields(
        rendered,
        report_language=language,
        expected_values=VALUES,
    )


def test_contract_rejects_unknown_locale_and_non_five_field_input() -> None:
    with pytest.raises(ValueError, match="unsupported_report_language"):
        client_evidence_summary_has_five_fields(
            "",
            report_language="fr",
            expected_values=VALUES,
        )
    with pytest.raises(ValueError, match="expected_exactly_five"):
        client_evidence_summary_has_five_fields(
            "",
            report_language="en",
            expected_values=VALUES[:-1],
        )
    with pytest.raises(ValueError, match="expected_nonempty"):
        client_evidence_summary_has_five_fields(
            "Client Evidence Summary",
            report_language="en",
            expected_values=("",) * 5,
        )
