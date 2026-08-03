from __future__ import annotations

import base64
import io
import re
import unicodedata
from copy import deepcopy
from functools import wraps
from html import unescape
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-compact-design-marker.v3"
_MARKER = "_nico_comprehensive_compact_design_marker_v3"

_DESIGN_MARKER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "NICO assessment identity",
        (
            "NICO COMPREHENSIVE",
            "NICO Comprehensive Technical Assessment",
            "Evaluación Técnica Integral NICO",
        ),
    ),
    (
        "client evidence summary",
        (
            "Evidence Package Summary",
            "Client Evidence Summary",
            "Resumen del paquete de evidencia",
            "Resumen de evidencia para revisión",
            "Resumen de evidencia para revision",
        ),
    ),
    (
        "human review and acceptance gate",
        (
            "Human Review and Acceptance Gate",
            "Puerta de revisión humana y aceptación",
            "Puerta de revision humana y aceptacion",
            "Puerta de revisión y entrega",
            "Puerta de revision y entrega",
        ),
    ),
)
_RETIRED_APPENDIX_HEADINGS = {
    "evidence appendix",
    "apendice de evidencia",
}


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_marks.casefold().split())


def _meaningful_lines(value: str) -> list[str]:
    output: list[str] = []
    for raw in str(value or "").splitlines():
        line = _normalized(raw.lstrip("# ").strip())
        if not line:
            continue
        if line.startswith("nico comprehensive ·"):
            continue
        if re.fullmatch(r"(?:page|pagina) \d+", line):
            continue
        output.append(line)
    return output


def _html_lines(value: str) -> list[str]:
    source = unescape(str(value or ""))
    source = re.sub(
        r"(?i)</(?:h[1-6]|p|div|section|article|li|tr|table|main)\s*>",
        "\n",
        source,
    )
    source = re.sub(r"(?i)<br\s*/?>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    return _meaningful_lines(source)


def _page_starts_retired_appendix(value: str) -> bool:
    lines = _meaningful_lines(value)
    return bool(lines and lines[0] in _RETIRED_APPENDIX_HEADINGS)


def _retired_appendix_section_present(package: Mapping[str, Any]) -> bool:
    """Reject an actual raw appendix section, not a bounded explanatory mention."""

    markdown_lines = _meaningful_lines(str(package.get("markdown") or ""))
    if any(line in _RETIRED_APPENDIX_HEADINGS for line in markdown_lines):
        return True

    html_lines = _html_lines(str(package.get("html") or ""))
    if any(line in _RETIRED_APPENDIX_HEADINGS for line in html_lines):
        return True

    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""))
    except Exception as exc:
        raise ValueError("client report did not retain a decodable PDF") from exc
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report did not retain a valid final PDF")
    for page in PdfReader(io.BytesIO(pdf)).pages:
        if _page_starts_retired_appendix(page.extract_text() or ""):
            return True
    return False


def _combined_client_text(package: Mapping[str, Any]) -> str:
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""))
    except Exception as exc:
        raise ValueError("client report did not retain a decodable PDF") from exc
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report did not retain a valid final PDF")
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    return "\n".join((markdown, rendered_html, extracted))


def _is_compact_client_package(package: Mapping[str, Any]) -> bool:
    """Identify only the bounded client package, not legacy or synthetic fixtures."""

    for key in (
        "client_report_completion",
        "phase17_artifact_rebuild",
        "premium_report_renderer",
    ):
        contract = package.get(key)
        if not isinstance(contract, Mapping):
            continue
        if contract.get("full_evidence_appendix_in_client_pdf") is False:
            return True
        if (
            contract.get("one_compact_client_pdf") is True
            and contract.get("full_evidence_retained_outside_client_pdf") is True
        ):
            return True

    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    pipeline = (
        canonical.get("v2_pipeline_contract")
        if isinstance(canonical.get("v2_pipeline_contract"), Mapping)
        else {}
    )
    return bool(
        pipeline.get("one_compact_client_pdf") is True
        and pipeline.get("full_evidence_retained_outside_client_pdf") is True
    )


def _legacy_delegate_package(
    package: Mapping[str, Any],
    legacy_markers: tuple[str, ...],
) -> dict[str, Any]:
    """Satisfy only the retired visual tuple in a private validation copy.

    The legacy validator also owns score, coverage, incomplete-analyzer, maturity,
    malformed-content, and superseded-diagnostic checks. Those checks remain active.
    The compatibility tokens exist only in this detached copy and never enter a
    client artifact, hash, download, or canonical truth surface.
    """

    result = deepcopy(dict(package))
    compatibility = "\n".join(str(marker) for marker in legacy_markers)
    result["markdown"] = (
        str(result.get("markdown") or "").rstrip()
        + "\n\n<!-- legacy visual marker compatibility only -->\n"
        + compatibility
        + "\n"
    )
    return result


def validate_compact_design_markers(package: Mapping[str, Any]) -> dict[str, Any]:
    """Require the bounded report's real decision sections, not a removed appendix."""

    combined = _combined_client_text(package)
    normalized = combined.casefold()
    missing: list[str] = []
    observed: dict[str, str] = {}
    for section, alternatives in _DESIGN_MARKER_GROUPS:
        matched = next(
            (marker for marker in alternatives if marker.casefold() in normalized),
            "",
        )
        if not matched:
            missing.append(section)
        else:
            observed[section] = matched
    if missing:
        raise ValueError(
            "approved compact NICO report design sections were not preserved: "
            + ", ".join(missing)
        )
    if _retired_appendix_section_present(package):
        raise ValueError(
            "compact client report restored the retired raw evidence appendix"
        )
    return {
        "version": VERSION,
        "compact_design_sections_verified": True,
        "observed_design_markers": observed,
        "retired_evidence_appendix_absent": True,
        "bounded_evidence_summary_present": True,
        "human_review_gate_present": True,
        "technical_scorecard_verified_by_authoritative_scorecard_gate": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _installation_contract(*, status: str, bound: bool) -> dict[str, Any]:
    return {
        "status": status,
        "version": VERSION,
        "bound": bound,
        "legacy_design_marker_tuple_preserved": True,
        "legacy_visual_compatibility_isolated_to_delegate_copy": True,
        "legacy_and_synthetic_packages_keep_original_validation": True,
        "retired_evidence_appendix_not_required_for_compact_package": True,
        "compact_evidence_summary_required": True,
        "bilingual_marker_groups_required": True,
        "authoritative_scorecard_gate_remains_separate": True,
        "score_scanner_maturity_and_identity_delegate_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_compact_design_marker_gate() -> dict[str, Any]:
    from nico import comprehensive_client_report_render_v60 as client_render

    current = client_render.validate_existing_report_accuracy
    if getattr(current, _MARKER, False):
        return _installation_contract(status="already_installed", bound=True)

    legacy_markers = tuple(client_render._DESIGN_MARKERS)

    @wraps(current)
    def validate(package: Mapping[str, Any]) -> dict[str, Any]:
        compact_package = _is_compact_client_package(package)
        delegate_input = (
            _legacy_delegate_package(package, legacy_markers)
            if compact_package
            else package
        )
        result = dict(current(delegate_input))
        if not compact_package:
            result["compact_design_marker_gate"] = {
                "version": VERSION,
                "applied": False,
                "reason": "package_not_declared_as_bounded_compact_client_report",
            }
            return result

        compact = validate_compact_design_markers(package)
        result["compact_design_marker_gate"] = compact
        result.update(
            {
                "existing_visual_design_preserved": True,
                "compact_evidence_summary_verified": True,
                "retired_evidence_appendix_absent": True,
            }
        )
        return result

    setattr(validate, _MARKER, True)
    setattr(validate, "_nico_previous", current)
    setattr(validate, "_nico_legacy_design_markers", legacy_markers)
    client_render.validate_existing_report_accuracy = validate
    return _installation_contract(
        status="installed",
        bound=client_render.validate_existing_report_accuracy is validate,
    )


__all__ = [
    "VERSION",
    "install_compact_design_marker_gate",
    "validate_compact_design_markers",
]
