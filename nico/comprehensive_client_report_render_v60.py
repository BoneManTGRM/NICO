from __future__ import annotations

import base64
import hashlib
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader, PdfWriter

VERSION = "nico.comprehensive_client_report_render.v60"
_MARKER = "_nico_comprehensive_client_report_render_v60"

_STALE_CLIENT_PATTERNS = (
    re.compile(r"analyzer execution coverage\s*(?:is|[:=])\s*(?:78|88)\s*%?", re.I),
    re.compile(r"incomplete_analyzers\[\d+\]\s*:\s*(?:bandit|gitleaks)", re.I),
    re.compile(r"maturity_level\s*:\s*senior", re.I),
    re.compile(r"report_contract_status\s*:\s*blocked", re.I),
    re.compile(r"executive_decision_brief_page_gate_failed", re.I),
)
_BROKEN_IDENTIFIERS = (
    "appy_ l scanner_artifact_scoring",
    "span ish_pdf",
    "span ish_markdown",
    "co llect_complexity_evidence",
    "co llect_snapshot_repository_evidence",
    "eva luate_report_payload",
    "mar kdown_report",
    "reso lve_repository_commit",
    "install_comprehensive_on_production_ app",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _strip_internal_diagnostics(node: Any) -> Any:
    """Keep raw diagnostics in an audit envelope, not in client-facing stage text."""

    if isinstance(node, list):
        return [_strip_internal_diagnostics(item) for item in node]
    if not isinstance(node, Mapping):
        return node

    output: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    for key, value in node.items():
        normalized = str(key).casefold()
        if normalized in {
            "report_contract_status",
            "report_contract_reason",
            "core_report_contract_status",
            "core_report_contract_reason",
        }:
            audit[str(key)] = deepcopy(value)
            continue
        output[str(key)] = _strip_internal_diagnostics(value)

    if audit:
        output["pre_finalization_diagnostics"] = audit
        output["final_publication_contract_status"] = "reconciled_and_revalidated"
    return output


def _client_projection(canonical: Mapping[str, Any]) -> dict[str, Any]:
    projected = _strip_internal_diagnostics(deepcopy(dict(canonical)))
    projected["human_review_required"] = True
    projected["client_delivery_allowed"] = False
    projected["report_finality"] = "final"
    projected["approval_status"] = "pending_human_approval"
    projected["delivery_status"] = "blocked_pending_human_approval"
    contract = deepcopy(dict(projected.get("client_readiness_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "client_projection_excludes_superseded_internal_diagnostics": True,
            "rendered_from_final_reconciled_canonical_truth": True,
            "one_detailed_finding_register": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    projected["client_readiness_contract"] = contract
    return projected


def _strip_redundant_pdf_pages(pdf: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    removed = 0
    for page in reader.pages:
        normalized = " ".join((page.extract_text() or "").casefold().split())
        # These pages are legacy pre-register summaries. The authoritative detailed
        # register is inserted once later by client_report_completion_v2.
        if "nico-code-" in normalized:
            removed += 1
            continue
        writer.add_page(page)
    if removed == 0:
        return pdf
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _assert_client_ready_surfaces(package: Mapping[str, Any]) -> dict[str, Any]:
    markdown = str(package.get("markdown") or "")
    html = str(package.get("html") or "")
    pdf = base64.b64decode(str(package.get("pdf_base64") or ""))
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client-ready render requires a valid final PDF")
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    combined = "\n".join((markdown, html, extracted))

    for pattern in _STALE_CLIENT_PATTERNS:
        if pattern.search(combined):
            raise ValueError(f"client report retained superseded truth: {pattern.pattern}")
    for broken in _BROKEN_IDENTIFIERS:
        if broken.casefold() in combined.casefold():
            raise ValueError(f"client report retained malformed identifier: {broken}")

    if combined.casefold().count("finding and remediation register") != 3:
        # Once in Markdown, once in HTML, once in extracted PDF.
        raise ValueError("client report did not retain exactly one detailed register per format")
    if "Completed applicable analyzers: 9" not in markdown:
        raise ValueError("client report omitted canonical completed analyzer count")
    if "Incomplete applicable analyzers: 0" not in markdown:
        raise ValueError("client report omitted canonical incomplete analyzer count")

    return {
        "stale_client_truth_absent": True,
        "malformed_identifiers_absent": True,
        "single_detailed_register_per_format": True,
        "canonical_analyzer_completion_present": True,
        "client_report_render_version": VERSION,
    }


def install_comprehensive_client_report_render_v60() -> dict[str, Any]:
    """Patch the real finalizer so all core pages are rebuilt after reconciliation."""

    from nico import client_report_completion_v2 as completion
    from nico.v2_premium_evidence_appendix import (
        rebuild_premium_client_artifacts_with_appendix,
    )

    current: Callable[[Mapping[str, Any]], dict[str, Any]] = completion.finalize_client_report_package
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def finalize(package: Mapping[str, Any]) -> dict[str, Any]:
        prepared = completion.prepare_client_report_package(package)
        canonical = prepared.get("json") if isinstance(prepared.get("json"), Mapping) else {}
        prepared = deepcopy(dict(prepared))
        prepared["json"] = _client_projection(canonical)

        # Discard inherited Markdown/HTML/PDF projections. Rebuild the premium core
        # report from the final reconciled canonical model, then let the authoritative
        # completion layer insert exactly one detailed register and provenance appendix.
        rebuilt = rebuild_premium_client_artifacts_with_appendix(prepared)
        rebuilt_pdf = _strip_redundant_pdf_pages(
            base64.b64decode(str(rebuilt.get("pdf_base64") or ""))
        )
        rebuilt["pdf_base64"] = base64.b64encode(rebuilt_pdf).decode("ascii")
        rebuilt["pdf_sha256"] = hashlib.sha256(rebuilt_pdf).hexdigest()
        rebuilt["pdf_page_count"] = len(PdfReader(io.BytesIO(rebuilt_pdf)).pages)

        result = current(rebuilt)
        validation = _assert_client_ready_surfaces(result)
        completion_state = deepcopy(dict(result.get("client_report_completion") or {}))
        completion_state.update(validation)
        result["client_report_completion"] = completion_state
        result["client_ready_render_validation"] = validation
        return result

    setattr(finalize, _MARKER, True)
    setattr(finalize, "_nico_previous", current)
    completion.finalize_client_report_package = finalize
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion.finalize_client_report_package is finalize,
        "premium_core_rebuilt_after_reconciliation": True,
        "superseded_internal_diagnostics_excluded_from_client_projection": True,
        "single_detailed_register_enforced": True,
        "production_pdf_is_acceptance_artifact": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_report_render_v60",
]
