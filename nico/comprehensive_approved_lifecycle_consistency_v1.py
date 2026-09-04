from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Callable

from pypdf import PdfReader

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256

VERSION = "nico.comprehensive_approved_lifecycle_consistency.v1"

_STATUS_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        r"\breview state\s*:\s*(?:pending human approval|pending)\b",
        "Review state: Approved",
    ),
    (
        r"\bapproval state\s*:\s*(?:pending human approval|pending)\b",
        "Approval state: Approved",
    ),
    (
        r"\breviewer identity\s*:\s*pending\b",
        "Reviewer identity: Recorded in the human review certificate",
    ),
    (
        r"\breviewer authorization\s*:\s*pending\b",
        "Reviewer authorization: Recorded",
    ),
    (r"\bdecision\s*:\s*pending\b", "Decision: Approved"),
    (
        r"\bclient delivery\s*:\s*(?:blocked|not authorized)\b",
        "Client delivery: Controlled separately",
    ),
    (
        r"\bclient delivery (?:is )?not authorized\b",
        "Client delivery is controlled separately",
    ),
    (
        r"\bhuman-review checklist remains unchecked\b",
        "Human-review checklist completion is retained in the approval certificate",
    ),
    (
        r"\bestado de revisi[oó]n\s*:\s*(?:aprobaci[oó]n humana pendiente|pendiente)\b",
        "Estado de revisión: Aprobada",
    ),
    (
        r"\bestado de aprobaci[oó]n\s*:\s*(?:aprobaci[oó]n humana pendiente|pendiente)\b",
        "Estado de aprobación: Aprobada",
    ),
    (
        r"\bidentidad del revisor\s*:\s*pendiente\b",
        "Identidad del revisor: Registrada en el certificado de revisión humana",
    ),
    (
        r"\bautorizaci[oó]n del revisor\s*:\s*pendiente\b",
        "Autorización del revisor: Registrada",
    ),
    (r"\bdecisi[oó]n\s*:\s*pendiente\b", "Decisión: Aprobada"),
    (
        r"\bentrega al cliente\s*:\s*(?:bloqueada|no autorizada)\b",
        "Entrega al cliente: Controlada por separado",
    ),
    (
        r"\bla entrega al cliente (?:no est[aá] autorizada|permanece bloqueada)\b",
        "La entrega al cliente se controla por separado",
    ),
)

_FORBIDDEN_APPROVED_PATTERNS: tuple[str, ...] = (
    r"\bpending human approval\b",
    r"\bhuman approval pending\b",
    r"\bhuman decision pending\b",
    r"\breview state\s*:\s*pending\b",
    r"\bapproval state\s*:\s*pending\b",
    r"\breviewer identity\s*:\s*pending\b",
    r"\breviewer authorization\s*:\s*pending\b",
    r"\bdecision\s*:\s*pending\b",
    r"\bclient delivery blocked\b",
    r"\bclient delivery (?:is )?not authorized\b",
    r"\baprobaci[oó]n humana pendiente\b",
    r"\bdecisi[oó]n humana pendiente\b",
    r"\bestado de revisi[oó]n\s*:\s*pendiente\b",
    r"\bestado de aprobaci[oó]n\s*:\s*pendiente\b",
    r"\bidentidad del revisor\s*:\s*pendiente\b",
    r"\bautorizaci[oó]n del revisor\s*:\s*pendiente\b",
    r"\bdecisi[oó]n\s*:\s*pendiente\b",
    r"\bentrega al cliente bloqueada\b",
    r"\bentrega al cliente no autorizada\b",
)


def _replace_status_text(value: str, base: Callable[[str], str]) -> str:
    output = base(str(value or ""))
    for pattern, replacement in _STATUS_REPLACEMENTS:
        output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)
    return output


def _pending(value: Any) -> bool:
    normalized = " ".join(str(value or "").strip().casefold().replace("_", " ").split())
    return normalized in {
        "pending",
        "pending human approval",
        "human approval pending",
        "blocked pending human approval",
        "pendiente",
        "aprobación humana pendiente",
        "aprobacion humana pendiente",
        "bloqueada",
        "no autorizada",
        "not authorized",
        "blocked",
    }


def _finalize_metadata(
    value: Any,
    *,
    reviewer: str,
    reviewer_role: str,
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, list):
        return [
            _finalize_metadata(
                item,
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                path=path,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _finalize_metadata(
                item,
                reviewer=reviewer,
                reviewer_role=reviewer_role,
                path=path,
            )
            for item in value
        )
    if not isinstance(value, Mapping):
        return value

    output: dict[str, Any] = {}
    for raw_key, raw_item in value.items():
        key = str(raw_key)
        normalized_key = key.strip().casefold().replace("-", "_").replace(" ", "_")
        item = _finalize_metadata(
            raw_item,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            path=(*path, normalized_key),
        )
        if normalized_key in {"review_state", "approval_state", "review_status", "approval_status"} and _pending(item):
            item = "approved"
        elif normalized_key in {"reviewer_identity", "reviewer"} and _pending(item):
            item = reviewer
        elif normalized_key in {"reviewer_authorization", "reviewer_role"} and _pending(item):
            item = reviewer_role
        elif normalized_key == "decision" and _pending(item) and any(
            token in {"review", "review_decision", "approval", "approval_record", "acceptance"}
            for token in path
        ):
            item = "approved"
        elif normalized_key in {"delivery_status", "client_delivery_status", "client_delivery"} and _pending(item):
            item = "certificate_controlled"
        elif normalized_key == "client_delivery_allowed":
            item = False
        output[key] = item
    return output


def _pdf_text(encoded: str) -> str:
    try:
        raw = base64.b64decode(str(encoded or ""), validate=True)
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError("comprehensive_approved_report_consistency_pdf_invalid") from exc
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def assert_approved_lifecycle_consistency(package: Mapping[str, Any]) -> None:
    canonical = package.get("json")
    if not isinstance(canonical, Mapping) or not canonical:
        raise ValueError("comprehensive_approved_report_consistency_json_missing")
    surfaces = {
        "json": json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str),
        "markdown": str(package.get("markdown") or ""),
        "html": str(package.get("html") or ""),
        "pdf": _pdf_text(str(package.get("pdf_base64") or "")),
    }
    for surface, text in surfaces.items():
        for pattern in _FORBIDDEN_APPROVED_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                raise ValueError(
                    f"comprehensive_approved_report_lifecycle_inconsistent:{surface}"
                )


def install_approved_lifecycle_consistency() -> dict[str, Any]:
    from nico import comprehensive_approved_report_v1 as approved

    if getattr(approved, "_nico_approved_lifecycle_consistency_v1_installed", False):
        return {
            "artifact_schema": VERSION,
            "installed": True,
            "cross_format_fail_closed": True,
        }

    original_replace = approved._replace_finality_text

    def replace_finality_text(value: str) -> str:
        return _replace_status_text(value, original_replace)

    approved._replace_finality_text = replace_finality_text
    original_build = approved.build_approved_report_package

    def build_consistent_approved_report(
        package: Mapping[str, Any],
        *,
        reviewer: str,
        reviewer_role: str,
        decision_reason: str,
        decided_at: str,
    ) -> dict[str, Any]:
        output = original_build(
            package,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision_reason=decision_reason,
            decided_at=decided_at,
        )
        canonical = _finalize_metadata(
            deepcopy(output.get("json") or {}),
            reviewer=reviewer,
            reviewer_role=reviewer_role,
        )
        if not isinstance(canonical, dict) or not canonical:
            raise ValueError("comprehensive_approved_report_consistency_json_missing")
        output["json"] = canonical
        output["canonical_truth_sha256"] = canonical_sha256(canonical)
        if isinstance(output.get("assessment"), Mapping):
            output["assessment"] = _finalize_metadata(
                deepcopy(output["assessment"]),
                reviewer=reviewer,
                reviewer_role=reviewer_role,
            )
        markdown = replace_finality_text(str(output.get("markdown") or ""))
        rendered_html = replace_finality_text(str(output.get("html") or ""))
        output["markdown"] = markdown
        output["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        output["html"] = rendered_html
        output["html_sha256"] = hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
        assert_approved_lifecycle_consistency(output)
        output["approved_lifecycle_consistency"] = {
            "artifact_schema": VERSION,
            "status": "valid",
            "cross_format_verified": True,
            "technical_analysis_regenerated": False,
            "client_delivery_allowed": False,
        }
        return output

    approved.build_approved_report_package = build_consistent_approved_report
    approved._nico_approved_lifecycle_consistency_v1_installed = True
    return {
        "artifact_schema": VERSION,
        "installed": True,
        "cross_format_fail_closed": True,
        "json_bound": True,
        "markdown_bound": True,
        "html_bound": True,
        "pdf_bound": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_approved_lifecycle_consistency",
    "install_approved_lifecycle_consistency",
]
