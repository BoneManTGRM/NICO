from __future__ import annotations

from collections.abc import Sequence


_SUMMARY_CONTRACTS = {
    "es-MX": {
        "heading": "Resumen de evidencia del cliente",
        "layouts": (
            {
                "following_heading": "Separación de ejecución y disposición",
                "preamble_markers": (
                    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
                    "ENTREGA AL CLIENTE BLOQUEADA",
                ),
            },
            {
                "following_heading": (
                    "El triaje técnico y la disposición humana están separados"
                ),
                "preamble_markers": (
                    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
                    "ENTREGA AL CLIENTE BLOQUEADA",
                    "Campo Valor",
                ),
            },
        ),
        "labels": (
            "Nombre del cliente",
            "Nombre del proyecto",
            "Contacto técnico principal",
            "Método de acceso",
            "Alcance autorizado",
        ),
    },
    "en": {
        "heading": "Client Evidence Summary",
        "layouts": (
            {
                "following_heading": "Execution and disposition are separate",
                "preamble_markers": (
                    "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · "
                    "CLIENT DELIVERY BLOCKED",
                ),
            },
            {
                "following_heading": (
                    "Technical triage and human disposition are separate"
                ),
                "preamble_markers": (
                    "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · "
                    "CLIENT DELIVERY BLOCKED",
                    "Field Value",
                ),
            },
        ),
        "labels": (
            "Client name",
            "Project name",
            "Primary technical contact",
            "Access method",
            "Authorized scope",
        ),
    },
}

_MAX_SUMMARY_PREAMBLE_CHARS = 1000


def _occurrences(
    value: str,
    needle: str,
    *,
    start: int,
    stop: int,
) -> tuple[int, ...]:
    positions: list[int] = []
    search_at = start
    while search_at < stop:
        position = value.find(needle, search_at, stop)
        if position < 0:
            break
        positions.append(position)
        search_at = position + len(needle)
    return tuple(positions)


def client_evidence_summary_has_five_fields(
    rendered_text: str,
    *,
    report_language: str,
    expected_values: Sequence[str],
) -> bool:
    """Verify five engagement fields inside one bounded summary section.

    The client PDF has two approved layouts. The direct client-ready projection
    uses the execution/disposition heading, while the current Phase 1 workload
    extension uses the technical-triage/human-disposition heading. Selecting the
    nearest approved boundary keeps values elsewhere in the PDF from satisfying
    this contract.
    """

    contract = _SUMMARY_CONTRACTS.get(report_language)
    if contract is None:
        raise ValueError(f"unsupported_report_language:{report_language}")
    if len(expected_values) != 5:
        raise ValueError("expected_exactly_five_client_evidence_values")

    compact = " ".join(str(rendered_text).split())
    values = tuple(" ".join(str(value).split()) for value in expected_values)
    if any(not value for value in values):
        raise ValueError("expected_nonempty_client_evidence_values")
    heading = str(contract["heading"])
    labels = tuple(str(label) for label in contract["labels"])
    layouts = tuple(contract["layouts"])

    search_at = 0
    while True:
        heading_at = compact.find(heading, search_at)
        if heading_at < 0:
            return False
        content_at = heading_at + len(heading)
        next_heading_at = compact.find(heading, content_at)
        section_limit = next_heading_at if next_heading_at >= 0 else len(compact)
        boundary_candidates = sorted(
            (
                position,
                tuple(str(value) for value in layout["preamble_markers"]),
            )
            for layout in layouts
            for position in _occurrences(
                compact,
                str(layout["following_heading"]),
                start=content_at,
                stop=section_limit,
            )
        )
        if boundary_candidates:
            boundary_at, preamble_markers = boundary_candidates[0]
            window = compact[heading_at:boundary_at]
            label_positions: list[int] = []
            label_search_at = len(heading)
            for label in labels:
                position = window.find(label, label_search_at)
                if position < 0:
                    label_positions = []
                    break
                label_positions.append(position)
                label_search_at = position + len(label)
            if label_positions:
                first_label_at = label_positions[0]
                preamble_search_at = len(heading)
                preamble_valid = (
                    first_label_at - preamble_search_at
                    <= _MAX_SUMMARY_PREAMBLE_CHARS
                )
                for marker in preamble_markers:
                    marker_at = window.find(
                        marker,
                        preamble_search_at,
                        first_label_at,
                    )
                    if marker_at < 0:
                        preamble_valid = False
                        break
                    preamble_search_at = marker_at + len(marker)
                if not preamble_valid:
                    search_at = content_at
                    continue
                values_bound_to_labels = all(
                    expected in window[
                        label_positions[index] + len(labels[index]) :
                        label_positions[index + 1]
                        if index + 1 < len(label_positions)
                        else len(window)
                    ]
                    for index, expected in enumerate(values)
                )
                if values_bound_to_labels:
                    return True
        search_at = content_at
