from __future__ import annotations

import base64
import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Response

import nico.comprehensive_api_controller as controller_module
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_report_package import (
    _canonical_hash,
    _markdown,
    _pdf,
    _semantic_html,
)
from nico.comprehensive_spanish_canonical_report_v87 import (
    render_spanish_html,
    render_spanish_markdown,
    render_spanish_pdf,
)
from nico.decision_grade_accepted_edition_guard_v1 import validate_accepted_edition


VERSION = "nico.comprehensive_same_run_locale_report.v3"
ROUTE = "/assessment/comprehensive-run/{run_id}/localized-report/{report_language}"
PDF_ROUTE = f"{ROUTE}/pdf"
SUPPORTED_REPORT_LANGUAGES = ("en", "es-MX")
MAX_LOCALIZED_MARKDOWN_BYTES = 4 * 1024 * 1024


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected
        in {
            str(item).upper()
            for item in (getattr(route, "methods", set()) or set())
        }
    )


def _normalize_report_language(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.lower() == "en":
        return "en"
    if raw.lower() in {"es-mx", "es_mx"}:
        return "es-MX"
    raise ValueError("unsupported_report_language")


def _render_inputs(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    identity = (
        deepcopy(dict(canonical.get("identity") or {}))
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    stages = [
        deepcopy(dict(item))
        for item in canonical.get("stage_summaries") or []
        if isinstance(item, Mapping)
    ]
    generated_at = str(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
        or ""
    )
    return identity, assessment, stages, generated_at


def _validate_status_canonical_identity(
    status: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, str]:
    """Fail closed when a terminal status is paired with another run's JSON."""

    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    pairs = (
        ("run_id", status.get("run_id"), identity.get("run_id")),
        ("repository", status.get("repository"), identity.get("repository")),
        ("commit_sha", status.get("commit_sha"), identity.get("commit_sha")),
        (
            "evidence_ledger_id",
            status.get("evidence_ledger_id"),
            identity.get("evidence_ledger_id"),
        ),
    )
    resolved: dict[str, str] = {}
    for field, status_value, canonical_value in pairs:
        status_text = str(status_value or "").strip()
        canonical_text = str(canonical_value or "").strip()
        if status_text and canonical_text and status_text != canonical_text:
            raise ValueError(f"status_canonical_{field}_mismatch")
        resolved[field] = status_text or canonical_text

    reports = (
        status.get("reports") if isinstance(status.get("reports"), Mapping) else {}
    )
    status_report_id = str(reports.get("report_id") or "").strip()
    canonical_report_id = str(
        canonical.get("report_id") or identity.get("report_id") or ""
    ).strip()
    if (
        status_report_id
        and canonical_report_id
        and status_report_id != canonical_report_id
    ):
        raise ValueError("status_canonical_report_id_mismatch")
    resolved["report_id"] = status_report_id or canonical_report_id

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    status_language = str(status.get("report_language") or "").strip()
    canonical_languages = [
        str(value).strip()
        for value in (
            identity.get("report_language"),
            identity.get("locale"),
            canonical.get("report_language"),
            canonical.get("locale"),
            assessment.get("report_language"),
            assessment.get("locale"),
        )
        if str(value or "").strip()
    ]
    if not canonical_languages:
        raise ValueError("canonical_report_language_required")
    normalized_canonical_languages = {
        _normalize_report_language(value) for value in canonical_languages
    }
    if len(normalized_canonical_languages) != 1:
        raise ValueError("canonical_report_language_inconsistent")
    canonical_language = next(iter(normalized_canonical_languages))
    if status_language and _normalize_report_language(status_language) != canonical_language:
        raise ValueError("status_canonical_report_language_mismatch")
    resolved["report_language"] = canonical_language

    for required in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        if not resolved[required]:
            raise ValueError(f"canonical_{required}_required")
    if reports and not resolved["report_id"]:
        raise ValueError("source_report_id_required")
    return resolved


def _source_lifecycle_projection(
    status: Mapping[str, Any],
    reports: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Project source-run lifecycle truth without applying locale-artifact policy."""

    record = (
        status.get("record")
        if isinstance(status.get("record"), Mapping)
        else {}
    )

    def authoritative(field: str, default: Any = None) -> Any:
        for container in (status, record):
            if field in container and container.get(field) is not None:
                return deepcopy(container.get(field))
        return deepcopy(default)

    run_status = str(authoritative("status", "unknown") or "unknown")
    normalized_run_status = run_status.strip().casefold()
    raw_human_review_completed = bool(
        authoritative("human_review_completed", False)
    )
    client_delivery_allowed = bool(authoritative("client_delivery_allowed", False))
    response_projection = (
        status.get("response_projection")
        if isinstance(status.get("response_projection"), Mapping)
        else {}
    )
    if normalized_run_status == "approved" and not raw_human_review_completed:
        raise ValueError("authoritative_approved_state_requires_completed_review")
    approved = (
        normalized_run_status == "approved" and raw_human_review_completed
    )
    rejected_requested = normalized_run_status in {"rejected", "declined"}
    rejected = (
        rejected_requested
        and raw_human_review_completed
        and response_projection.get("rejection_review_integrity_valid") is True
    )
    human_review_completed = approved or rejected
    if client_delivery_allowed and not approved:
        raise ValueError("delivery_authorization_requires_approved_run")
    delivery_integrity_invalid = (
        response_projection.get("delivery_authorization_invalidated") is True
        or (
            client_delivery_allowed
            and response_projection.get("delivery_authorization_integrity_valid")
            is not True
        )
    )
    if delivery_integrity_invalid:
        client_delivery_allowed = False
    if approved:
        approval_status = "approved_final"
        human_review_status = "approved"
    elif rejected:
        approval_status = "rejected"
        human_review_status = "rejected"
    else:
        approval_status = "pending_human_approval"
        human_review_status = "pending"

    if delivery_integrity_invalid:
        delivery_status = "blocked_authorization_integrity"
        client_delivery_status = "blocked"
    elif client_delivery_allowed:
        delivery_status = "authorized"
        client_delivery_status = "authorized"
    elif approved:
        delivery_status = "pending_authorization"
        client_delivery_status = "pending_authorization"
    elif rejected:
        delivery_status = "blocked_rejected"
        client_delivery_status = "blocked"
    else:
        delivery_status = "blocked_pending_human_approval"
        client_delivery_status = "blocked"

    return {
        "run_status": run_status,
        "human_review_required": bool(authoritative("human_review_required", True)),
        "human_review_completed": human_review_completed,
        "client_delivery_allowed": client_delivery_allowed,
        "approval_status": approval_status,
        "delivery_status": delivery_status,
        "human_review_status": human_review_status,
        "client_delivery_status": client_delivery_status,
        "delivery_authorization_integrity_valid": not delivery_integrity_invalid,
    }


def _localized_artifact_lifecycle(
    source: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    localized_json: Mapping[str, Any],
    *,
    regenerated: bool,
) -> dict[str, Any]:
    """Keep reused source bytes exact; fail closed for every regenerated byte set."""

    if not regenerated:
        return deepcopy(dict(source))
    return {
        "run_status": source.get("run_status"),
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "approval_status": str(
            artifacts.get("approval_status")
            or localized_json.get("approval_status")
            or "pending_human_approval"
        ),
        "delivery_status": str(
            artifacts.get("delivery_status")
            or localized_json.get("delivery_status")
            or "blocked_pending_human_approval"
        ),
        "human_review_status": str(
            artifacts.get("human_review_status")
            or localized_json.get("human_review_status")
            or "pending"
        ),
        "client_delivery_status": str(
            artifacts.get("client_delivery_status")
            or localized_json.get("client_delivery_status")
            or "blocked"
        ),
    }


_PROVIDER_ACCESS_STATIC_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "Rate-limit status: A provider limitation was recorded.",
        "Estado de límite de solicitudes: Se registró una limitación del proveedor.",
    ),
    (
        "Rate-limit status: No active provider limit was recorded.",
        "Estado de límite de solicitudes: Sin limitación activa registrada.",
    ),
    ("Human review: Required.", "Revisión humana: Obligatoria."),
    (
        "Human approval: Pending explicit reviewer action.",
        "Aprobación humana: Pendiente de una acción explícita del revisor.",
    ),
    ("Client delivery: Not authorized.", "Entrega al cliente: No autorizada."),
)

_PROVIDER_ACCESS_PREFIX_PAIRS: tuple[tuple[str, str], ...] = (
    ("Provider", "Proveedor"),
    ("Repository identity", "Identidad del repositorio"),
    ("Immutable revision", "Revisión inmutable"),
    ("Access mode", "Modo de acceso"),
    ("Provider credential used", "Credencial del proveedor utilizada"),
    (
        "Required source evidence complete",
        "Evidencia fuente requerida completa",
    ),
    ("Pagination complete", "Paginación completa"),
    ("Source fingerprint", "Huella digital de la fuente"),
    ("Exact-source locators", "Localizadores de fuente exacta"),
    ("Assessment snapshot identity", "Identidad de la instantánea de evaluación"),
    ("Collection limitations recorded", "Limitaciones de recopilación registradas"),
)

_PROVIDER_ACCESS_VALUE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Anonymous public", "Público anónimo"),
    ("Authenticated read-only", "Autenticado de solo lectura"),
    ("Undetermined", "No determinado"),
    ("Yes", "Sí"),
)

_PROVIDER_CAPABILITY_PAIRS: tuple[tuple[str, str], ...] = (
    ("Repository", "Repositorio"),
    ("Commits", "Commits"),
    ("Branches", "Ramas"),
    ("Source tree", "Árbol de fuentes"),
    ("Source objects", "Objetos fuente"),
    ("Tags", "Etiquetas"),
    ("Change requests", "Solicitudes de cambio"),
    ("Pipeline runs", "Ejecuciones de canalización"),
    ("Pipeline jobs", "Trabajos de canalización"),
    ("Environments", "Entornos"),
    ("Deployments", "Despliegues"),
    ("Issues or work items", "Incidencias o elementos de trabajo"),
    ("Releases", "Versiones"),
    ("Exact-source links", "Enlaces de fuente exacta"),
)

_PROVIDER_CAPABILITY_STATE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Collected", "Recopilado"),
    ("Supported but empty", "Compatible, pero vacío"),
    ("Collected with explicit limits", "Recopilado con límites explícitos"),
    (
        "Unavailable without read-only authentication",
        "No disponible sin autenticación de solo lectura",
    ),
    (
        "Unavailable with the current permission",
        "No disponible con el permiso actual",
    ),
    (
        "Unavailable due to provider limitation",
        "No disponible por una limitación del proveedor",
    ),
    (
        "Unavailable due to repository configuration",
        "No disponible por la configuración del repositorio",
    ),
    (
        "Unavailable because the provider rate limit was reached",
        "No disponible porque se alcanzó el límite de solicitudes del proveedor",
    ),
    (
        "Collection failed and was not treated as complete",
        "La recopilación falló y no se trató como completa",
    ),
    ("Not applicable", "No aplicable"),
    ("Not assessed", "No evaluado"),
)


def _provider_translation_map(
    pairs: tuple[tuple[str, str], ...], *, english: bool
) -> dict[str, str]:
    return {
        spanish if english else source_english: source_english if english else spanish
        for source_english, spanish in pairs
    }


def _localized_provider_access_line(value: Any, report_language: str) -> str:
    """Translate the bounded provider-access evidence authored by the runtime."""

    line = str(value or "")
    english = report_language == "en"
    for english_text, spanish_text in _PROVIDER_ACCESS_STATIC_PAIRS:
        source, target = (
            (spanish_text, english_text) if english else (english_text, spanish_text)
        )
        if line == source:
            return target

    source_capability_prefix = "Capacidad " if english else "Capability "
    if line.startswith(source_capability_prefix):
        match = re.fullmatch(r"[^ ]+ (.+): (.+)\.", line)
        if not match:
            raise ValueError("provider_access_capability_evidence_invalid")
        labels = _provider_translation_map(
            _PROVIDER_CAPABILITY_PAIRS, english=english
        )
        states = _provider_translation_map(
            _PROVIDER_CAPABILITY_STATE_PAIRS, english=english
        )
        label, state = match.groups()
        if label not in labels or state not in states:
            raise ValueError("provider_access_capability_translation_missing")
        target_prefix = "Capability" if english else "Capacidad"
        return f"{target_prefix} {labels[label]}: {states[state]}."

    for english_prefix, spanish_prefix in _PROVIDER_ACCESS_PREFIX_PAIRS:
        source_prefix, target_prefix = (
            (spanish_prefix, english_prefix)
            if english
            else (english_prefix, spanish_prefix)
        )
        marker = source_prefix + ": "
        if not line.startswith(marker) or not line.endswith("."):
            continue
        translated_value = line[len(marker) : -1]
        values = _provider_translation_map(
            _PROVIDER_ACCESS_VALUE_PAIRS, english=english
        )
        translated_value = values.get(translated_value, translated_value)
        if english_prefix == "Exact-source locators":
            if english:
                translated_value = re.sub(r" presentes$", " present", translated_value)
            else:
                translated_value = re.sub(r" present$", " presentes", translated_value)
        return f"{target_prefix}: {translated_value}."
    return line


def _localize_provider_access_evidence(
    canonical: dict[str, Any], report_language: str
) -> None:
    """Localize the provider stage in both canonical stage projections."""

    containers: list[Any] = [canonical.get("stage_summaries")]
    assessment = canonical.get("assessment")
    if isinstance(assessment, Mapping):
        containers.append(assessment.get("stage_summaries"))
    for stages in containers:
        if not isinstance(stages, list):
            continue
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            if stage.get("stage_id") != "repository_and_delivery_evidence":
                continue
            evidence = stage.get("evidence")
            if isinstance(evidence, list):
                stage["evidence"] = [
                    _localized_provider_access_line(item, report_language)
                    for item in evidence
                ]


def _localized_draft_view(
    canonical: Mapping[str, Any],
    report_language: str,
) -> dict[str, Any]:
    """Create a locale-only render input without carrying exact-artifact approval."""

    view = deepcopy(dict(canonical))
    identity = (
        deepcopy(dict(view.get("identity") or {}))
        if isinstance(view.get("identity"), Mapping)
        else {}
    )
    assessment = (
        deepcopy(dict(view.get("assessment") or {}))
        if isinstance(view.get("assessment"), Mapping)
        else {}
    )
    for container in (view, identity, assessment):
        container["report_language"] = report_language
        container["locale"] = report_language
    view["identity"] = identity
    view["assessment"] = assessment
    _localize_provider_access_evidence(view, report_language)

    # These objects bind one exact byte set. A localized regeneration is a new draft.
    for field in (
        "artifacts",
        "artifact_manifest",
        "approval",
        "accepted_edition",
        "accepted_edition_manifest_sha256",
        "lifecycle",
    ):
        view.pop(field, None)
    view.update(
        {
            "review_package_ready": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "report_finality": "automated_draft",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
        }
    )
    return view


def _truth_records(canonical: Mapping[str, Any], identity_field: str) -> tuple[Any, ...]:
    ignored = {"artifacts", "artifact_manifest", "approval", "lifecycle"}
    output: set[tuple[Any, ...]] = set()

    def visit(value: Any, key: str = "") -> None:
        if key in ignored:
            return
        if isinstance(value, Mapping):
            if value.get(identity_field) not in (None, ""):
                output.add(
                    (
                        str(value.get(identity_field)),
                        str(value.get("finding_id") or ""),
                        str(value.get("priority") or value.get("severity") or ""),
                        str(
                            value.get("location")
                            or value.get("exact_source")
                            or value.get("source_path")
                            or ""
                        ),
                        str(value.get("proposed_disposition") or ""),
                        str(value.get("human_disposition") or ""),
                    )
                )
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(canonical)
    return tuple(sorted(output))


def _assessment_truth_projection(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    maturity = (
        assessment.get("maturity_signal")
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    engagement = (
        canonical.get("engagement_metadata")
        if isinstance(canonical.get("engagement_metadata"), Mapping)
        else {}
    )
    # Scanner applicability is a deterministic projection of the retained exact-run
    # evidence. Historical pending drafts can retain a pre-applicability scanner list
    # (for example, Node-only tools recorded as failed for a Python-only repository),
    # while the current renderer correctly projects those records as not applicable.
    # Compare both sides through the same bounded projection so this derived repair does
    # not look like an immutable assessment mutation. Scores, findings, candidates, and
    # exact-run identity below continue to come from the untouched canonical object.
    from nico.comprehensive_authoritative_scanner_truth_v62 import (
        reconcile_authoritative_scanner_truth,
    )

    scanner_canonical = reconcile_authoritative_scanner_truth(canonical)
    scanner_assessment = (
        scanner_canonical.get("assessment")
        if isinstance(scanner_canonical.get("assessment"), Mapping)
        else {}
    )
    scanners = scanner_canonical.get("scanner_execution_records")
    if not isinstance(scanners, list):
        scanners = scanner_assessment.get("scanner_execution_records") or []
    return {
        "identity": tuple(
            str(identity.get(field) or "")
            for field in ("repository", "commit_sha", "run_id", "evidence_ledger_id")
        ),
        "scores": (
            assessment.get("technical_score"),
            assessment.get("canonical_evidence_adjusted_score"),
            maturity.get("score"),
            maturity.get("presented_score"),
        ),
        "scanners": tuple(
            sorted(
                (
                    str(item.get("scanner_name") or item.get("tool") or ""),
                    str(item.get("state") or item.get("status") or ""),
                    item.get("completed"),
                    item.get("exact_commit_match"),
                    str(item.get("artifact_hash") or ""),
                    len(item.get("findings") or []),
                )
                for item in scanners
                if isinstance(item, Mapping)
            )
        ),
        "candidates": _truth_records(canonical, "candidate_id"),
        "findings": _truth_records(canonical, "finding_id"),
        "sections": tuple(
            (
                str(item.get("id") or item.get("section_id") or ""),
                item.get("score"),
                item.get("presented_score"),
            )
            for item in assessment.get("sections") or []
            if isinstance(item, Mapping)
        ),
        "stage_ids": tuple(
            str(item.get("stage_id") or "")
            for item in canonical.get("stage_summaries") or []
            if isinstance(item, Mapping)
        ),
        "identity_engagement": tuple(
            identity.get(field)
            for field in (
                "customer_name",
                "project_name",
                "primary_technical_contact",
                "access_method",
                "authorized_scope",
                "engagement_metadata_sha256",
            )
        ),
        "engagement": tuple(
            engagement.get(field)
            for field in (
                "client_name",
                "project_name",
                "primary_technical_contact",
                "access_method",
                "authorized_scope",
            )
        ),
    }


def _assemble_target(
    canonical: Mapping[str, Any], report_language: str
) -> dict[str, Any]:
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    source_projection = _assessment_truth_projection(canonical)
    localized = rebuild_client_artifacts(
        {"json": _localized_draft_view(canonical, report_language)}
    )
    localized_json = (
        localized.get("json")
        if isinstance(localized.get("json"), Mapping)
        else {}
    )
    if not localized_json:
        raise ValueError("localized_full_assembler_json_required")
    if _assessment_truth_projection(localized_json) != source_projection:
        raise ValueError("localized_assessment_truth_parity_mismatch")
    if (
        localized.get("approval_status") != "pending_human_approval"
        or localized.get("delivery_status") != "blocked_pending_human_approval"
        or localized.get("client_delivery_allowed") is not False
    ):
        raise ValueError("localized_artifact_approval_invalidation_failed")
    return localized


def _english_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity, assessment, stages, generated_at = _render_inputs(canonical)
    repository = str(identity.get("repository") or "repository")
    markdown = _markdown(identity, assessment, stages, generated_at)
    title = f"NICO Comprehensive Technical Assessment — {repository}"
    html = _semantic_html(markdown, title)
    encoded, error, page_count = _pdf(identity, assessment, stages, generated_at)
    if error or not encoded:
        raise ValueError(
            f"canonical English PDF renderer failed: {error or 'empty PDF'}"
        )
    pdf_bytes = base64.b64decode(encoded)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("canonical English PDF renderer returned an invalid PDF")
    return {
        "markdown": markdown,
        "html": html,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_page_count": int(page_count or 0),
    }


def _spanish_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = str(identity.get("repository") or "repository")
    markdown = render_spanish_markdown(canonical)
    title = f"Evaluación Técnica Integral NICO — {repository}"
    html = render_spanish_html(markdown, title)
    pdf_bytes, page_count = render_spanish_pdf(canonical)
    return {
        "markdown": markdown,
        "html": html,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_page_count": int(page_count or 0),
    }


def _render_target(
    canonical: Mapping[str, Any], report_language: str
) -> dict[str, Any]:
    if report_language not in SUPPORTED_REPORT_LANGUAGES:
        raise ValueError("unsupported_report_language")
    return _assemble_target(canonical, report_language)


def _bounded_markdown(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("localized_report_markdown_required")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_LOCALIZED_MARKDOWN_BYTES:
        raise ValueError("localized_report_markdown_too_large")
    return value, hashlib.sha256(encoded).hexdigest()


def build_same_run_locale_markdown_projection(
    status: Mapping[str, Any],
    report_language: str,
) -> dict[str, Any]:
    """Return only the bounded Markdown view used by the assessment workspace.

    The canonical package can contain tens of megabytes of JSON, HTML, manifests,
    CSV, and base64 PDF data. Copy-Markdown callers use none of those bodies. Keeping
    them out of this response prevents an exact-run reconnect from competing with a
    second full artifact assembly while retaining immutable identity, canonical truth,
    and fail-closed review/delivery lifecycle metadata.
    """

    target_language = _normalize_report_language(report_language)
    if status.get("terminal") is not True:
        raise ValueError("terminal_report_required")

    reports = (
        status.get("reports") if isinstance(status.get("reports"), Mapping) else {}
    )
    canonical = reports.get("json") if isinstance(reports.get("json"), Mapping) else {}
    if not canonical:
        raise ValueError("terminal_canonical_report_json_required")
    canonical_copy = deepcopy(dict(canonical))
    identity_binding = _validate_status_canonical_identity(status, canonical_copy)

    expected_truth_sha256 = str(reports.get("canonical_truth_sha256") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_truth_sha256):
        raise ValueError(
            "canonical_truth_hash_required"
            if not expected_truth_sha256
            else "canonical_truth_hash_invalid"
        )
    if not controller_module._canonical_truth_hash_integrity_bound(
        reports,
        canonical_copy,
    ):
        raise ValueError("canonical_truth_hash_mismatch")
    canonical_truth_sha256 = expected_truth_sha256.casefold()

    source_language = _normalize_report_language(identity_binding["report_language"])
    source_lifecycle = _source_lifecycle_projection(status, reports, canonical_copy)
    if source_lifecycle["approval_status"] == "approved_final":
        # An approved source lifecycle may be projected only when the accepted exact
        # byte set remains valid. Pending/rejected runs avoid this PDF decode entirely.
        if not controller_module._final_report_package_integrity_bound(reports):
            raise ValueError("source_report_artifact_integrity_invalid")
        try:
            source_pdf = base64.b64decode(
                str(reports.get("pdf_base64") or ""), validate=True
            )
        except Exception as exc:
            raise ValueError("accepted_edition_pdf_required") from exc
        _accepted_source_binding(
            status,
            reports,
            identity_binding,
            source_language,
            source_pdf,
        )

    regenerated = target_language != source_language
    if regenerated:
        localized_view = _localized_draft_view(canonical_copy, target_language)
        from nico.phase17_canonical_artifact_rebuild_v1 import (
            build_localized_markdown_projection,
        )

        localized = build_localized_markdown_projection({"json": localized_view})
        localized_json = (
            localized.get("json")
            if isinstance(localized.get("json"), Mapping)
            else {}
        )
        if not localized_json:
            raise ValueError("localized_markdown_prepared_canonical_required")
        if _assessment_truth_projection(localized_json) != _assessment_truth_projection(
            canonical_copy
        ):
            raise ValueError("localized_assessment_truth_parity_mismatch")
        markdown_value = localized.get("markdown")
        artifact_lifecycle = _localized_artifact_lifecycle(
            source_lifecycle,
            {},
            localized_json,
            regenerated=True,
        )
    else:
        markdown_value = reports.get("markdown")
        artifact_lifecycle = deepcopy(source_lifecycle)

    markdown, markdown_sha256 = _bounded_markdown(markdown_value)
    if not regenerated:
        claimed_markdown_sha256 = str(reports.get("markdown_sha256") or "").strip()
        if claimed_markdown_sha256:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", claimed_markdown_sha256):
                raise ValueError("source_report_markdown_hash_invalid")
            if claimed_markdown_sha256.casefold() != markdown_sha256:
                raise ValueError("source_report_markdown_hash_mismatch")

    source_report_id = identity_binding["report_id"]
    return {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "projection_kind": "localized_markdown",
        "response_bounded": True,
        "run_id": identity_binding["run_id"],
        "repository": identity_binding["repository"],
        "commit_sha": identity_binding["commit_sha"],
        "evidence_ledger_id": identity_binding["evidence_ledger_id"],
        "source_report_id": source_report_id,
        "source_report_language": source_language,
        "report_language": target_language,
        "same_canonical_run": True,
        "assessment_rerun": False,
        "canonical_truth_preserved": True,
        "canonical_truth_sha256": canonical_truth_sha256,
        "source_integrity_sha256": str(status.get("integrity_sha256") or ""),
        "human_review_required": source_lifecycle["human_review_required"],
        "human_review_completed": source_lifecycle["human_review_completed"],
        "client_delivery_allowed": source_lifecycle["client_delivery_allowed"],
        "approval_status": source_lifecycle["approval_status"],
        "delivery_status": source_lifecycle["delivery_status"],
        "human_review_status": source_lifecycle["human_review_status"],
        "client_delivery_status": source_lifecycle["client_delivery_status"],
        "canonical_run_lifecycle": deepcopy(source_lifecycle),
        "approval_state_mutated": False,
        "delivery_state_mutated": False,
        "localized_artifact_approval_invalidated": regenerated,
        "localized_artifact_requires_new_approval": regenerated,
        "localized_artifact_lifecycle": deepcopy(artifact_lifecycle),
        "report": {
            "service_id": "comprehensive",
            "report_id": source_report_id,
            "presentation_language": target_language,
            "canonical_truth_sha256": canonical_truth_sha256,
            "markdown": markdown,
            "markdown_sha256": markdown_sha256,
            "response_bounded": True,
            "human_review_required": artifact_lifecycle["human_review_required"],
            "human_review_completed": artifact_lifecycle["human_review_completed"],
            "client_delivery_allowed": artifact_lifecycle[
                "client_delivery_allowed"
            ],
            "approval_status": artifact_lifecycle["approval_status"],
            "delivery_status": artifact_lifecycle["delivery_status"],
            "human_review_status": artifact_lifecycle["human_review_status"],
            "client_delivery_status": artifact_lifecycle[
                "client_delivery_status"
            ],
        },
    }


def _safe_repository(value: Any) -> str:
    normalized = re.sub(
        r"[^A-Za-z0-9_.-]+", "-", str(value or "repository")
    ).strip("-")
    return normalized or "repository"


def _localized_filename(
    *, canonical: Mapping[str, Any], run_id: str, report_language: str
) -> str:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = _safe_repository(identity.get("repository"))
    locale = "en" if report_language == "en" else "es-MX"
    return (
        f"nico-comprehensive-assessment-{repository}-{run_id}-{locale}-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )


def _accepted_filename(
    *, canonical: Mapping[str, Any], run_id: str, report_language: str
) -> str:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    repository = _safe_repository(identity.get("repository"))
    locale = "en" if report_language == "en" else "es-MX"
    return (
        f"nico-comprehensive-assessment-{repository}-{run_id}-{locale}-"
        "APPROVED-ACCEPTED-EDITION.pdf"
    )


def _claimed_object_hash_valid(
    value: Mapping[str, Any],
    claim_field: str,
) -> bool:
    payload = deepcopy(dict(value))
    claimed = str(payload.pop(claim_field, "") or "").strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", claimed):
        return False
    actual = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return claimed == actual


def _accepted_source_binding(
    status: Mapping[str, Any],
    reports: Mapping[str, Any],
    identity_binding: Mapping[str, str],
    source_language: str,
    pdf_bytes: bytes,
) -> dict[str, str]:
    lifecycle = _source_lifecycle_projection(
        status,
        reports,
        reports.get("json") or {},
    )
    if lifecycle["approval_status"] != "approved_final":
        return {}

    accepted = status.get("accepted_edition")
    if not isinstance(accepted, Mapping):
        raise ValueError("accepted_edition_identity_required")
    if not _claimed_object_hash_valid(
        accepted,
        "accepted_edition_manifest_sha256",
    ):
        raise ValueError("accepted_edition_manifest_hash_mismatch")

    review = accepted.get("review")
    if not isinstance(review, Mapping) or not _claimed_object_hash_valid(
        review,
        "approval_certificate_sha256",
    ):
        raise ValueError("accepted_edition_review_certificate_hash_mismatch")
    if str(review.get("decision") or "").strip().casefold() != "approved":
        raise ValueError("accepted_edition_review_decision_invalid")
    if (
        accepted.get("accepted_edition") is not True
        or accepted.get("client_delivery_allowed") is not False
        or str(accepted.get("delivery_status") or "") != "pending_authorization"
    ):
        raise ValueError("accepted_edition_lifecycle_invalid")

    for field in ("run_id", "repository", "commit_sha"):
        if str(accepted.get(field) or "").strip() != str(
            identity_binding.get(field) or ""
        ).strip():
            raise ValueError(f"accepted_edition_identity_mismatch:{field}")
    accepted_language = _normalize_report_language(
        accepted.get("report_language")
    )
    if accepted_language != source_language:
        raise ValueError("accepted_edition_language_mismatch")

    digests = accepted.get("artifact_digests")
    pdf_digest = digests.get("pdf") if isinstance(digests, Mapping) else None
    accepted_pdf_sha256 = str(
        pdf_digest.get("sha256") if isinstance(pdf_digest, Mapping) else ""
    ).strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", accepted_pdf_sha256):
        raise ValueError("accepted_edition_pdf_digest_required")
    if accepted_pdf_sha256 != hashlib.sha256(pdf_bytes).hexdigest():
        raise ValueError("accepted_edition_pdf_digest_mismatch")
    if isinstance(pdf_digest, Mapping) and pdf_digest.get("size_bytes") is not None:
        try:
            accepted_pdf_size = int(pdf_digest["size_bytes"])
        except (TypeError, ValueError) as exc:
            raise ValueError("accepted_edition_pdf_size_invalid") from exc
        if accepted_pdf_size != len(pdf_bytes):
            raise ValueError("accepted_edition_pdf_size_mismatch")

    validation = validate_accepted_edition(
        reports,
        accepted,
        trusted_report_identity=identity_binding,
    )
    if (
        validation.get("status") != "valid"
        or list(validation.get("validation_errors") or [])
    ):
        raise ValueError("accepted_edition_manifest_invalid")

    return {
        "pdf_sha256": accepted_pdf_sha256,
        "report_language": accepted_language,
        "manifest_sha256": str(
            accepted.get("accepted_edition_manifest_sha256") or ""
        ).strip().casefold(),
    }


def _frozen_source_pdf_response(
    status: Mapping[str, Any], report_language: str
) -> Response | None:
    """Return an already-persisted source-language PDF without re-rendering it.

    For the run's source language only, validate the stored PDF bytes, exact run
    identity, source locale, and canonical JSON hash before returning bytes unchanged.
    A historical artifact whose stored JSON no longer proves the asserted truth hash
    cannot safely carry that hash in a current-release response and therefore fails
    closed.
    """

    target_language = _normalize_report_language(report_language)
    if status.get("terminal") is not True:
        raise ValueError("terminal_report_required")

    reports = (
        status.get("reports") if isinstance(status.get("reports"), Mapping) else {}
    )
    canonical = (
        reports.get("json") if isinstance(reports.get("json"), Mapping) else {}
    )
    if not canonical:
        return None

    canonical_copy = deepcopy(dict(canonical))
    identity_binding = _validate_status_canonical_identity(status, canonical_copy)
    source_language = _normalize_report_language(
        identity_binding["report_language"]
    )
    if target_language != source_language:
        return None

    encoded_pdf = reports.get("pdf_base64")
    if not isinstance(encoded_pdf, str) or not encoded_pdf:
        return None

    try:
        pdf_bytes = base64.b64decode(encoded_pdf, validate=True)
    except Exception as exc:
        raise ValueError("source_report_pdf_invalid") from exc
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("source_report_pdf_invalid")

    actual_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    stored_pdf_sha256 = str(reports.get("pdf_sha256") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", stored_pdf_sha256):
        raise ValueError("source_report_pdf_hash_required")
    if stored_pdf_sha256.casefold() != actual_pdf_sha256:
        raise ValueError("source_report_pdf_hash_mismatch")

    identity = (
        canonical_copy.get("identity")
        if isinstance(canonical_copy.get("identity"), Mapping)
        else {}
    )
    status_run_id = str(status.get("run_id") or "").strip()
    canonical_run_id = str(identity.get("run_id") or "").strip()
    if status_run_id and canonical_run_id and status_run_id != canonical_run_id:
        raise ValueError("source_report_run_identity_mismatch")
    run_id = status_run_id or canonical_run_id
    if not run_id:
        raise ValueError("run_id_required")

    status_repository = str(status.get("repository") or "").strip()
    canonical_repository = str(identity.get("repository") or "").strip()
    if (
        status_repository
        and canonical_repository
        and status_repository != canonical_repository
    ):
        raise ValueError("source_report_repository_identity_mismatch")

    status_commit = str(status.get("commit_sha") or "").strip()
    canonical_commit = str(identity.get("commit_sha") or "").strip()
    if status_commit and canonical_commit and status_commit != canonical_commit:
        raise ValueError("source_report_commit_identity_mismatch")

    stored_truth_sha256 = str(reports.get("canonical_truth_sha256") or "").strip()
    if not stored_truth_sha256:
        raise ValueError("canonical_truth_hash_required")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", stored_truth_sha256):
        raise ValueError("canonical_truth_hash_invalid")
    if not controller_module._final_report_package_integrity_bound(reports):
        if not controller_module._canonical_truth_hash_integrity_bound(
            reports, canonical_copy
        ):
            raise ValueError("canonical_truth_hash_mismatch")
        raise ValueError("source_report_artifact_integrity_invalid")

    source_lifecycle = _source_lifecycle_projection(
        status,
        reports,
        canonical_copy,
    )
    accepted_binding = _accepted_source_binding(
        status,
        reports,
        identity_binding,
        source_language,
        pdf_bytes,
    )

    stored_filename = str(reports.get("pdf_filename") or "").replace('"', "").strip()
    if stored_filename:
        filename = stored_filename
    elif accepted_binding:
        filename = _accepted_filename(
            canonical=canonical_copy,
            run_id=run_id,
            report_language=target_language,
        )
    else:
        filename = _localized_filename(
            canonical=canonical_copy,
            run_id=run_id,
            report_language=target_language,
        )
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-NICO-Run-ID": run_id,
        "X-NICO-Commit-SHA": identity_binding["commit_sha"],
        "X-NICO-Report-Language": target_language,
        "X-NICO-Canonical-Truth-SHA256": stored_truth_sha256,
        "X-NICO-PDF-SHA256": actual_pdf_sha256,
        "X-NICO-Artifact-SHA256": actual_pdf_sha256,
        "X-NICO-Frozen-Source-Artifact": "true",
        "X-NICO-Assessment-Rerun": "false",
        "X-NICO-Approval-Status": str(source_lifecycle["approval_status"]),
        "X-NICO-Delivery-Status": str(source_lifecycle["delivery_status"]),
        "X-NICO-Client-Delivery-Allowed": str(
            source_lifecycle["client_delivery_allowed"]
        ).lower(),
        "X-NICO-Localized-Artifact-Requires-New-Approval": "false",
    }
    if accepted_binding:
        headers.update(
            {
                "X-NICO-Accepted-PDF-SHA256": accepted_binding["pdf_sha256"],
                "X-NICO-Accepted-Edition-Language": accepted_binding[
                    "report_language"
                ],
                "X-NICO-Accepted-Edition-Manifest-SHA256": accepted_binding[
                    "manifest_sha256"
                ],
            }
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )


def build_same_run_locale_report(
    status: Mapping[str, Any],
    report_language: str,
) -> dict[str, Any]:
    """Render a presentation locale from one terminal immutable run.

    This function is deliberately read-only. It neither resumes the assessment nor
    changes review, approval, acceptance, or delivery state. Both language outputs are
    derived from the exact canonical JSON already attached to the terminal report.
    """

    target_language = _normalize_report_language(report_language)
    if status.get("terminal") is not True:
        raise ValueError("terminal_report_required")

    reports = (
        status.get("reports") if isinstance(status.get("reports"), Mapping) else {}
    )
    canonical = (
        reports.get("json") if isinstance(reports.get("json"), Mapping) else {}
    )
    if not canonical:
        raise ValueError("terminal_canonical_report_json_required")
    canonical_copy = deepcopy(dict(canonical))
    identity_binding = _validate_status_canonical_identity(status, canonical_copy)
    expected_truth_sha256 = str(reports.get("canonical_truth_sha256") or "").strip()
    if not expected_truth_sha256:
        raise ValueError("canonical_truth_hash_required")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_truth_sha256):
        raise ValueError("canonical_truth_hash_invalid")
    if not controller_module._canonical_truth_hash_integrity_bound(
        reports,
        canonical_copy,
    ):
        raise ValueError("canonical_truth_hash_mismatch")
    canonical_truth_sha256 = expected_truth_sha256.casefold()

    source_language = _normalize_report_language(
        identity_binding["report_language"]
    )
    source_lifecycle = _source_lifecycle_projection(
        status,
        reports,
        canonical_copy,
    )
    source_pdf_bytes: bytes | None = None
    encoded_source_pdf = reports.get("pdf_base64")
    if isinstance(encoded_source_pdf, str) and encoded_source_pdf:
        try:
            source_pdf_bytes = base64.b64decode(encoded_source_pdf, validate=True)
        except Exception as exc:
            raise ValueError("source_report_pdf_invalid") from exc
        if not source_pdf_bytes.startswith(b"%PDF"):
            raise ValueError("source_report_pdf_invalid")
        source_pdf_sha256 = str(reports.get("pdf_sha256") or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_pdf_sha256):
            raise ValueError("source_report_pdf_hash_required")
        if source_pdf_sha256.casefold() != hashlib.sha256(source_pdf_bytes).hexdigest():
            raise ValueError("source_report_pdf_hash_mismatch")
    if not controller_module._final_report_package_integrity_bound(reports):
        raise ValueError("source_report_artifact_integrity_invalid")
    if source_lifecycle["approval_status"] == "approved_final":
        if source_pdf_bytes is None:
            raise ValueError("accepted_edition_pdf_required")
        _accepted_source_binding(
            status,
            reports,
            identity_binding,
            source_language,
            source_pdf_bytes,
        )
    source_artifacts_reused = False
    force_pending_draft_regeneration = (
        status.get("_nico_force_pending_draft_artifact_regeneration") is True
        and source_lifecycle["approval_status"] == "pending_human_approval"
        and source_lifecycle["client_delivery_allowed"] is False
    )
    if target_language == source_language and not force_pending_draft_regeneration:
        markdown = reports.get("markdown")
        html = reports.get("html")
        encoded_pdf = reports.get("pdf_base64")
        if (
            isinstance(markdown, str)
            and isinstance(html, str)
            and isinstance(encoded_pdf, str)
            and encoded_pdf
        ):
            pdf_bytes = source_pdf_bytes
            if pdf_bytes is None:
                raise ValueError("source_report_pdf_invalid")
            artifacts = {
                "markdown": markdown,
                "html": html,
                "pdf_base64": encoded_pdf,
                "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "pdf_page_count": reports.get("pdf_page_count"),
            }
            source_artifacts_reused = True
        else:
            artifacts = _render_target(canonical_copy, target_language)
    else:
        artifacts = _render_target(canonical_copy, target_language)

    run_id = identity_binding["run_id"]

    localized_artifact_json = (
        deepcopy(dict(artifacts.get("json") or {}))
        if isinstance(artifacts.get("json"), Mapping)
        else {}
    )
    regenerated = not source_artifacts_reused
    artifact_lifecycle = _localized_artifact_lifecycle(
        source_lifecycle,
        artifacts,
        localized_artifact_json,
        regenerated=regenerated,
    )

    source_report_id = str(reports.get("report_id") or "")
    result = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "run_id": run_id,
        "repository": identity_binding["repository"],
        "commit_sha": identity_binding["commit_sha"],
        "source_report_id": source_report_id,
        "source_report_language": source_language,
        "report_language": target_language,
        "same_canonical_run": True,
        "assessment_rerun": False,
        "canonical_truth_preserved": True,
        "canonical_truth_sha256": canonical_truth_sha256,
        "source_integrity_sha256": str(status.get("integrity_sha256") or ""),
        "human_review_required": source_lifecycle["human_review_required"],
        "human_review_completed": source_lifecycle["human_review_completed"],
        "client_delivery_allowed": source_lifecycle["client_delivery_allowed"],
        "approval_status": source_lifecycle["approval_status"],
        "delivery_status": source_lifecycle["delivery_status"],
        "human_review_status": source_lifecycle["human_review_status"],
        "client_delivery_status": source_lifecycle["client_delivery_status"],
        "canonical_run_lifecycle": deepcopy(source_lifecycle),
        "approval_state_mutated": False,
        "delivery_state_mutated": False,
        "localized_artifact_approval_invalidated": regenerated,
        "localized_artifact_requires_new_approval": regenerated,
        "localized_artifact_lifecycle": deepcopy(artifact_lifecycle),
        "report": {
            "service_id": "comprehensive",
            "report_id": source_report_id,
            "presentation_language": target_language,
            "canonical_truth_sha256": canonical_truth_sha256,
            # The endpoint's canonical JSON/hash always identify the immutable source
            # assessment. The full assembler's locale-specific draft JSON is exposed
            # separately because its language and exact-artifact lifecycle differ.
            "json": canonical_copy,
            "markdown": artifacts["markdown"],
            "html": artifacts["html"],
            "pdf_base64": artifacts["pdf_base64"],
            "pdf_filename": _localized_filename(
                canonical=canonical_copy,
                run_id=run_id,
                report_language=target_language,
            ),
            "pdf_sha256": artifacts["pdf_sha256"],
            "pdf_page_count": artifacts.get("pdf_page_count"),
            "human_review_required": artifact_lifecycle[
                "human_review_required"
            ],
            "human_review_completed": artifact_lifecycle[
                "human_review_completed"
            ],
            "client_delivery_allowed": artifact_lifecycle[
                "client_delivery_allowed"
            ],
            "approval_status": artifact_lifecycle["approval_status"],
            "delivery_status": artifact_lifecycle["delivery_status"],
            "human_review_status": artifact_lifecycle["human_review_status"],
            "client_delivery_status": artifact_lifecycle[
                "client_delivery_status"
            ],
            "localized_artifact_canonical_json_sha256": str(
                artifacts.get("canonical_json_sha256") or ""
            ),
        },
    }
    if localized_artifact_json:
        result["report"]["localized_artifact_json"] = localized_artifact_json
        result["report"]["localized_artifact_canonical_json"] = str(
            artifacts.get("canonical_json") or ""
        )
    for field in (
        "findings_csv",
        "findings_csv_sha256",
        "evidence_csv",
        "evidence_csv_sha256",
        "candidate_register_json",
        "candidate_register_sha256",
        "remediation_backlog_json",
        "remediation_backlog_sha256",
        "artifact_manifest",
        "evidence_manifest_json",
        "evidence_manifest_sha256",
        "draft_artifact_identity",
        "review_package_ready",
        "human_review_status",
        "client_delivery_status",
        "report_finality",
    ):
        if field in artifacts:
            result["report"][field] = deepcopy(artifacts[field])
    return result


def build_same_run_locale_pdf_response(
    status: Mapping[str, Any], report_language: str
) -> Response:
    frozen_source = _frozen_source_pdf_response(status, report_language)
    if frozen_source is not None:
        return frozen_source

    projection = build_same_run_locale_report(status, report_language)
    report = projection["report"]
    try:
        pdf_bytes = base64.b64decode(report["pdf_base64"], validate=True)
    except Exception as exc:
        raise ValueError("localized_report_pdf_invalid") from exc
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("localized_report_pdf_invalid")

    expected_sha256 = str(report.get("pdf_sha256") or "")
    actual_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("localized_report_pdf_hash_required")
    if expected_sha256.casefold() != actual_sha256:
        raise ValueError("localized_report_pdf_hash_mismatch")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{report["pdf_filename"]}"',
            "X-NICO-Run-ID": str(projection["run_id"]),
            "X-NICO-Commit-SHA": str(projection["commit_sha"]),
            "X-NICO-Report-Language": str(projection["report_language"]),
            "X-NICO-Canonical-Truth-SHA256": str(
                projection["canonical_truth_sha256"]
            ),
            "X-NICO-PDF-SHA256": actual_sha256,
            "X-NICO-Artifact-SHA256": actual_sha256,
            "X-NICO-Assessment-Rerun": "false",
            "X-NICO-Approval-Status": "pending_human_approval",
            "X-NICO-Delivery-Status": "blocked_pending_human_approval",
            "X-NICO-Client-Delivery-Allowed": "false",
            "X-NICO-Localized-Artifact-Requires-New-Approval": "true",
            "X-NICO-Localized-Artifact-Approval-Invalidated": "true",
            "X-NICO-Artifact-Finality": "automated_draft",
        },
    )


def _controller_status(target: FastAPI, run_id: str) -> Mapping[str, Any]:
    controller = getattr(target.state, "comprehensive_api_controller", None)
    artifact_reader = (
        getattr(controller, "status_artifact_read_only", None)
        if controller is not None
        else None
    )
    fallback_reader = (
        getattr(controller, "status_read_only", None)
        if controller is not None
        else None
    )
    reader = artifact_reader if callable(artifact_reader) else fallback_reader
    if controller is None or not callable(reader):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "blocked",
                "reason": "comprehensive_controller_unavailable",
            },
        )
    try:
        return reader(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_found",
                "reason": "comprehensive_run_not_found",
            },
        ) from exc


def _projection_http_error(exc: ValueError) -> HTTPException:
    reason = str(exc)
    status_code = 422 if reason == "unsupported_report_language" else 409
    return HTTPException(
        status_code=status_code,
        detail={"status": "blocked", "reason": reason},
    )


def install_same_run_locale_report(target: FastAPI) -> dict[str, Any]:
    """Install read-only bilingual report projection routes exactly once."""

    if _route_count(target, "GET", ROUTE) == 0:

        def localized_report(run_id: str, report_language: str) -> dict[str, Any]:
            try:
                status = _controller_status(target, run_id)
                return build_same_run_locale_markdown_projection(
                    status,
                    report_language,
                )
            except ValueError as exc:
                raise _projection_http_error(exc) from exc

        target.add_api_route(
            ROUTE,
            localized_report,
            methods=["GET"],
            tags=["comprehensive"],
        )
        target.openapi_schema = None

    if _route_count(target, "GET", PDF_ROUTE) == 0:

        def localized_report_pdf(run_id: str, report_language: str) -> Response:
            try:
                status = _controller_status(target, run_id)
                return build_same_run_locale_pdf_response(status, report_language)
            except ValueError as exc:
                raise _projection_http_error(exc) from exc

        target.add_api_route(
            PDF_ROUTE,
            localized_report_pdf,
            methods=["GET"],
            tags=["comprehensive"],
            response_class=Response,
        )
        target.openapi_schema = None

    route_count = _route_count(target, "GET", ROUTE)
    pdf_route_count = _route_count(target, "GET", PDF_ROUTE)
    status = {
        "artifact_schema": VERSION,
        "route": ROUTE,
        "route_count": route_count,
        "pdf_route": PDF_ROUTE,
        "pdf_route_count": pdf_route_count,
        "supported_report_languages": list(SUPPORTED_REPORT_LANGUAGES),
        "same_canonical_run": True,
        "assessment_rerun": False,
        "canonical_truth_preserved": True,
        "frozen_source_pdf_reused_without_rerender": True,
        "cross_language_projection_requires_canonical_hash": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    target.state.nico_same_run_locale_report = status
    return status


__all__ = [
    "PDF_ROUTE",
    "ROUTE",
    "SUPPORTED_REPORT_LANGUAGES",
    "VERSION",
    "build_same_run_locale_pdf_response",
    "build_same_run_locale_report",
    "install_same_run_locale_report",
]
