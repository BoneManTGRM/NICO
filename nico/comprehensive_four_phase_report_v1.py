from __future__ import annotations

import base64
import hashlib
import io
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from nico.comprehensive_four_phase_model_v1 import (
    VERSION,
    _copy,
    _spanish,
    _text,
    apply_four_phase_program,
    build_four_phase_program,
    four_phase_markdown,
    repair_four_phase_markdown,
)
from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf

_MARKER = "__nico_comprehensive_four_phase_report_v1__"
_ATTACH_MARKER = "__nico_comprehensive_four_phase_manifest_input_v1__"


def _html(markdown: str, canonical: Mapping[str, Any], spanish: bool) -> str:
    try:
        from nico.client_ready_html_v1 import render_client_html

        identity = (
            canonical.get("identity")
            if isinstance(canonical.get("identity"), Mapping)
            else {}
        )
        title = (
            "Evaluación Técnica Integral NICO"
            if spanish
            else (
                "NICO Comprehensive Technical Assessment - "
                + _text(identity.get("repository"))
            )
        )
        return render_client_html(markdown, title, spanish=spanish)
    except Exception:
        return "<html><body><pre>" + markdown + "</pre></body></html>"


def _canonical_hash(canonical: Mapping[str, Any]) -> str:
    try:
        from nico import comprehensive_report_package as base_report

        return base_report._canonical_hash(dict(canonical))
    except Exception:
        payload = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def _canonical_payload_digest(canonical: Mapping[str, Any]) -> str:
    """Hash canonical truth without recursive artifact self-references."""

    payload = deepcopy(dict(canonical))
    payload.pop("artifacts", None)
    payload.pop("artifact_manifest", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _synchronize_canonical_json_artifact_digest(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep existing canonical-json projections bound to final four-phase truth.

    Normal production publication now runs before the exact-artifact manifest is
    built, so that manifest computes every final digest from the already extended
    package. This compatibility step only repairs any earlier canonical-json
    projection supplied by a caller; the terminal manifest remains authoritative.
    """

    output = deepcopy(dict(canonical))
    digest = _canonical_payload_digest(output)

    artifact_lists: list[list[Any]] = []
    artifacts = output.get("artifacts")
    if isinstance(artifacts, list):
        artifact_lists.append(artifacts)

    manifest = output.get("artifact_manifest")
    if isinstance(manifest, Mapping):
        manifest_copy = deepcopy(dict(manifest))
        output["artifact_manifest"] = manifest_copy
        manifest_artifacts = manifest_copy.get("artifacts")
        if isinstance(manifest_artifacts, list):
            artifact_lists.append(manifest_artifacts)

    for artifact_list in artifact_lists:
        for index, value in enumerate(artifact_list):
            if not isinstance(value, Mapping):
                continue
            artifact = deepcopy(dict(value))
            if _text(artifact.get("artifact_type")).casefold() == "canonical_json":
                artifact["sha256"] = digest
            artifact_list[index] = artifact

    return output


def finalize_four_phase_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Publish the four-phase program into the existing Comprehensive package."""

    from pypdf import PdfReader

    result = deepcopy(dict(package))
    canonical = apply_four_phase_program(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _synchronize_canonical_json_artifact_digest(canonical)
    spanish = _spanish(canonical)
    markdown = repair_four_phase_markdown(
        str(result.get("markdown") or ""),
        canonical,
        spanish=spanish,
    )
    rendered_html = _html(markdown, canonical, spanish)
    encoded = str(result.get("pdf_base64") or "").strip()
    if not encoded:
        raise ValueError("NICO Comprehensive four-phase publication requires a PDF")
    pdf = apply_four_phase_pdf(
        base64.b64decode(encoded),
        canonical,
        spanish=spanish,
    )
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = [
        phase.get("title_es" if spanish else "title_en")
        for phase in canonical["four_phase_program"]["phases"]
    ]
    for surface_name, surface in (
        ("markdown", markdown),
        ("html", rendered_html),
        ("pdf", extracted),
    ):
        missing = [
            title
            for title in required
            if _text(title).casefold()
            not in _text(surface, 2_000_000).casefold()
        ]
        if missing:
            raise ValueError(
                f"four-phase {surface_name} publication omitted phases: "
                + ", ".join(missing)
            )

    count = len(reader.pages)
    result.update(
        {
            "json": canonical,
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_page_count": count,
            "core_report_page_count": count,
            "final_package_page_count": count,
            "canonical_truth_sha256": _canonical_hash(canonical),
            "four_phase_program": deepcopy(canonical["four_phase_program"]),
            "human_review_required": True,
            "client_delivery_allowed": canonical.get("client_delivery_allowed") is True,
        }
    )
    completion = _copy(result.get("client_report_completion"))
    completion.update(
        {
            "four_phase_report_version": VERSION,
            "four_phase_program_in_json": True,
            "four_phase_program_in_markdown": True,
            "four_phase_program_in_html": True,
            "four_phase_program_in_pdf": True,
            "four_phase_toc_matrix_present": True,
            "all_four_phases_present": True,
            "phase4_human_approval_boundary_preserved": True,
            "one_client_report": True,
        }
    )
    result["client_report_completion"] = completion
    for key in ("premium_report_renderer", "phase17_artifact_rebuild"):
        value = _copy(result.get(key))
        value.update(completion)
        result[key] = value
    return result


def install_comprehensive_four_phase_report_v1() -> dict[str, Any]:
    """Publish four-phase truth before immutable artifact digests are bound.

    The exact-artifact manifest is NICO's terminal byte-identity boundary. Canonical
    truth, Markdown, HTML, PDF navigation, and the page-two phase matrix must exist
    before that boundary computes hashes. Patching the manifest input also avoids a
    locale-order mutation: English and Spanish both consume the same pre-manifest
    producer instead of wrapping a locale-specific terminal finalizer after output.
    """

    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    current: Callable[..., dict[str, Any]] = manifest.attach_artifact_manifest
    if getattr(current, _ATTACH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "phase_count": 4,
            "publication_precedes_exact_artifact_binding": True,
            "detached_manifest_recomputed_after_four_phase_publication": True,
        }

    @wraps(current)
    def attach_artifact_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
        prepared = finalize_four_phase_report_package(package)
        return current(prepared)

    setattr(attach_artifact_manifest, _ATTACH_MARKER, True)
    setattr(attach_artifact_manifest, "_nico_previous", current)
    manifest.attach_artifact_manifest = attach_artifact_manifest
    return {
        "status": "installed",
        "version": VERSION,
        "bound": manifest.attach_artifact_manifest is attach_artifact_manifest,
        "phase_count": 4,
        "english_and_spanish_supported": True,
        "four_phase_program_in_json": True,
        "four_phase_program_in_markdown": True,
        "four_phase_program_in_html": True,
        "four_phase_program_in_pdf": True,
        "page_count_unchanged_before_manifest_supplement": True,
        "publication_precedes_exact_artifact_binding": True,
        "detached_manifest_recomputed_after_four_phase_publication": True,
        "one_client_report": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "apply_four_phase_pdf",
    "apply_four_phase_program",
    "build_four_phase_program",
    "finalize_four_phase_report_package",
    "four_phase_markdown",
    "install_comprehensive_four_phase_report_v1",
    "repair_four_phase_markdown",
]
