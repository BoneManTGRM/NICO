from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
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


def _html(markdown: str, canonical: Mapping[str, Any], spanish: bool) -> str:
    try:
        from nico.client_ready_html_v1 import render_client_html

        identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
        title = "Evaluación Técnica Integral NICO" if spanish else f"NICO Comprehensive Technical Assessment - {_text(identity.get('repository'))}"
        return render_client_html(markdown, title, spanish=spanish)
    except Exception:
        return "<html><body><pre>" + markdown + "</pre></body></html>"


def _canonical_hash(canonical: Mapping[str, Any]) -> str:
    try:
        from nico import comprehensive_report_package as base_report

        return base_report._canonical_hash(dict(canonical))
    except Exception:
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
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
    """Keep both canonical-json manifest copies bound to final four-phase truth.

    The upstream finalizer creates the self-excluding canonical payload digest before
    this report extension adds the four-phase program. Rebind only the canonical JSON
    artifact entries after that final truth is present. Other artifact digests, the
    detached manifest self-digest, scores, findings, and approval state remain intact.
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
    from pypdf import PdfReader

    result = deepcopy(dict(package))
    canonical = apply_four_phase_program(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    canonical = _synchronize_canonical_json_artifact_digest(canonical)
    spanish = _spanish(canonical)
    markdown = repair_four_phase_markdown(
        str(result.get("markdown") or ""), canonical, spanish=spanish
    )
    rendered_html = _html(markdown, canonical, spanish)
    encoded = str(result.get("pdf_base64") or "").strip()
    if not encoded:
        raise ValueError("NICO Comprehensive four-phase publication requires a PDF")
    pdf = apply_four_phase_pdf(base64.b64decode(encoded), canonical, spanish=spanish)
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
            "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode()).hexdigest(),
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


def _replace_aliases(original: Any, replacement: Any) -> int:
    count = 0
    for module in list(sys.modules.values()):
        try:
            if (
                module is not None
                and getattr(module, "finalize_client_report_package", None) is original
            ):
                setattr(module, "finalize_client_report_package", replacement)
                count += 1
        except Exception:
            continue
    return count


def install_comprehensive_four_phase_report_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current: Callable[..., dict[str, Any]] = completion.finalize_client_report_package
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "phase_count": 4,
        }

    @wraps(current)
    def finalize(package: Mapping[str, Any]) -> dict[str, Any]:
        return finalize_four_phase_report_package(current(package))

    setattr(finalize, _MARKER, True)
    setattr(finalize, "_nico_previous", current)
    completion.finalize_client_report_package = finalize
    rebound = _replace_aliases(current, finalize)
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion.finalize_client_report_package is finalize,
        "aliases_rebound": rebound,
        "phase_count": 4,
        "english_and_spanish_supported": True,
        "four_phase_program_in_json": True,
        "four_phase_program_in_markdown": True,
        "four_phase_program_in_html": True,
        "four_phase_program_in_pdf": True,
        "page_count_unchanged": True,
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
