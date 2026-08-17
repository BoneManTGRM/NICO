from __future__ import annotations

import base64
import hashlib
import html
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-exact-artifact-hash-binding.v1"
_MARKDOWN_MARKER = "__nico_exact_artifact_markdown_guide_v1__"
_DIGEST_INDEPENDENT_MANIFEST_MARKER = (
    "__nico_digest_independent_artifact_manifest_guide_v1__"
)
_ENTRIES_MARKER = "__nico_exact_artifact_entries_v1__"
_ATTACH_MARKER = "__nico_exact_artifact_attach_v1__"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_guide(identity: Mapping[str, str]) -> str:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    run = manifest._safe_filename(identity.get("run_id"), "run")
    detached_filename = f"nico-{run}-evidence-manifest.json"
    language = _text(identity.get("report_language"), 40).casefold()
    if language.startswith("es"):
        return (
            "## Manifiesto de artefactos del cliente\n\n"
            "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA\n\n"
            f"- Repositorio: {identity.get('repository') or 'No disponible'}\n"
            f"- Commit exacto: {identity.get('commit_sha') or 'No disponible'}\n"
            f"- ID de ejecución: {identity.get('run_id') or 'No disponible'}\n"
            f"- ID del registro de evidencia: {identity.get('evidence_ledger_id') or 'No disponible'}\n"
            f"- Manifiesto separado: {detached_filename}\n"
            "- Valores SHA-256 finales y tamaños en bytes: preservados en el manifiesto separado y en la identidad exacta del borrador después del renderizado\n\n"
            "## Registro de revisión humana y aprobación de artefactos exactos\n\n"
            "- Paquete de revisión listo: Sí\n"
            "- Aprobación humana: Pendiente\n"
            "- Entrega al cliente: Bloqueada\n"
            "- Identidad del revisor: Pendiente\n"
            "- Rol del revisor: Pendiente\n"
            "- Autorización del revisor: Pendiente\n"
            "- Decisión: Pendiente\n\n"
            "Instrucciones de verificación: vuelva a calcular el SHA-256 del PDF, JSON canónico, Markdown, HTML, CSV, registro de candidatos, trabajo pendiente de remediación y manifiesto separado; compare cada resultado con el manifiesto separado y la identidad del borrador exacto; confirme que coincidan el repositorio, commit exacto, ID de ejecución, registro de evidencia y fecha y hora de generación.\n\n"
            "Solo un revisor humano autorizado puede aprobar los hashes del PDF inmutable exacto, JSON canónico y manifiesto separado. Cualquier artefacto regenerado o sustituido crea un nuevo borrador automatizado e invalida la aprobación anterior.\n"
        )
    return (
        "## Client Artifact Manifest\n\n"
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n"
        f"- Repository: {identity.get('repository') or 'Not available'}\n"
        f"- Exact commit: {identity.get('commit_sha') or 'Not available'}\n"
        f"- Run ID: {identity.get('run_id') or 'Not available'}\n"
        f"- Evidence ledger ID: {identity.get('evidence_ledger_id') or 'Not available'}\n"
        f"- Detached manifest: {detached_filename}\n"
        "- Final SHA-256 values and byte sizes: retained in the detached manifest and exact draft identity after rendering\n\n"
        "## Human Review and Exact-Artifact Approval Record\n\n"
        "- Review package ready: Yes\n"
        "- Human approval: Pending\n"
        "- Client delivery: Blocked\n"
        "- Reviewer identity: Pending\n"
        "- Reviewer role: Pending\n"
        "- Reviewer authorization: Pending\n"
        "- Decision: Pending\n\n"
        "Verification instructions: recompute SHA-256 for the PDF, canonical JSON, Markdown, HTML, CSV, candidate register, remediation backlog, and detached manifest; compare each result with the detached manifest and draft identity; confirm the repository, exact commit, run ID, evidence ledger, and generated timestamp match.\n\n"
        "Only an authorized human reviewer may approve the exact immutable PDF, canonical JSON, and detached manifest digests. Any regenerated or replaced artifact creates a new automated draft and invalidates prior approval.\n"
    )


def _anticipated_markdown(context: Mapping[str, Any], guide: str) -> str:
    return str(context.get("markdown") or "").rstrip() + "\n\n" + guide


def _anticipated_html(context: Mapping[str, Any], guide: str) -> str:
    rendered = str(context.get("html") or "")
    section = (
        '<section data-nico-artifact-manifest="true"><pre>'
        + html.escape(guide)
        + "</pre></section>"
    )
    return (
        rendered.replace("</body>", section + "</body>", 1)
        if "</body>" in rendered
        else rendered + section
    )


def _artifact_bytes(result: Mapping[str, Any], artifact_type: str) -> bytes:
    text_fields = {
        "findings_csv": "findings_csv",
        "evidence_csv": "evidence_csv",
        "candidate_register_json": "candidate_register_json",
        "remediation_backlog_json": "remediation_backlog_json",
        "markdown_report": "markdown",
        "html_report": "html",
        "canonical_json": "canonical_json",
    }
    if artifact_type == "comprehensive_pdf":
        try:
            return base64.b64decode(str(result.get("pdf_base64") or ""), validate=True)
        except Exception as exc:
            raise ValueError("Comprehensive PDF could not be decoded for hash verification") from exc
    field = text_fields.get(artifact_type)
    if not field:
        raise ValueError(f"No retained content mapping exists for artifact type {artifact_type}")
    return str(result.get(field) or "").encode("utf-8")


def _validate_exact_artifact_hashes(result: Mapping[str, Any]) -> None:
    manifest = result.get("artifact_manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("Detached artifact manifest is missing")
    artifacts = [
        item for item in manifest.get("artifacts") or [] if isinstance(item, Mapping)
    ]
    if not artifacts:
        raise ValueError("Detached artifact manifest contains no artifacts")

    for item in artifacts:
        artifact_type = _text(item.get("artifact_type"), 100)
        content = _artifact_bytes(result, artifact_type)
        expected_sha = _text(item.get("sha256"), 100).lower()
        expected_size = item.get("size_bytes")
        actual_sha = _sha256(content)
        actual_size = len(content)
        if not expected_sha or actual_sha != expected_sha:
            raise ValueError(
                f"artifact {artifact_type} SHA-256 mismatch: {actual_sha} != {expected_sha or 'missing'}"
            )
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise ValueError(f"artifact {artifact_type} omitted an integer byte size")
        if actual_size != expected_size:
            raise ValueError(
                f"artifact {artifact_type} byte-size mismatch: {actual_size} != {expected_size}"
            )

    manifest_json = str(result.get("evidence_manifest_json") or "").encode("utf-8")
    expected_manifest_sha = _text(result.get("evidence_manifest_sha256"), 100).lower()
    if not manifest_json or _sha256(manifest_json) != expected_manifest_sha:
        raise ValueError("detached evidence manifest SHA-256 does not match retained bytes")

    canonical_json = str(result.get("canonical_json") or "").encode("utf-8")
    pdf = _artifact_bytes(result, "comprehensive_pdf")
    identity = result.get("draft_artifact_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("Exact draft artifact identity is missing")
    checks = {
        "pdf_sha256": _sha256(pdf),
        "canonical_json_sha256": _sha256(canonical_json),
        "evidence_manifest_sha256": _sha256(manifest_json),
    }
    for field, actual in checks.items():
        if _text(identity.get(field), 100).lower() != actual:
            raise ValueError(f"draft artifact identity {field} does not match retained bytes")
        if _text(result.get(field), 100).lower() != actual:
            raise ValueError(f"package {field} does not match retained bytes")


def install_comprehensive_exact_artifact_hash_binding_v1() -> dict[str, Any]:
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico import comprehensive_manifest_navigation_v1 as navigation

    current_markdown = manifest._markdown_manifest
    if not getattr(current_markdown, _MARKDOWN_MARKER, False):

        @wraps(current_markdown)
        def _markdown_manifest(
            identity: Mapping[str, str],
            entries: list[dict[str, Any]],
            *,
            pdf_sha256: str,
            canonical_json_sha256: str,
            manifest_sha256: str,
        ) -> str:
            del entries, pdf_sha256, canonical_json_sha256, manifest_sha256
            return _manifest_guide(identity)

        setattr(_markdown_manifest, _MARKDOWN_MARKER, True)
        setattr(
            _markdown_manifest,
            _DIGEST_INDEPENDENT_MANIFEST_MARKER,
            True,
        )
        setattr(_markdown_manifest, "_nico_previous", current_markdown)
        manifest._markdown_manifest = _markdown_manifest

    current_entries = manifest._preliminary_entries
    if not getattr(current_entries, _ENTRIES_MARKER, False):

        @wraps(current_entries)
        def _preliminary_entries(
            canonical: Mapping[str, Any], exports: Mapping[str, bytes]
        ) -> list[dict[str, Any]]:
            entries = list(current_entries(canonical, exports))
            context = navigation._CONTEXT.get()
            identity = manifest._canonical_identity(canonical)
            guide = _manifest_guide(identity)
            contents = {
                "markdown_report": _anticipated_markdown(context, guide).encode("utf-8"),
                "html_report": _anticipated_html(context, guide).encode("utf-8"),
            }
            output: list[dict[str, Any]] = []
            for raw in entries:
                item = deepcopy(dict(raw))
                artifact_type = _text(item.get("artifact_type"), 100)
                content = contents.get(artifact_type)
                if content is not None:
                    item["sha256"] = _sha256(content)
                    item["size_bytes"] = len(content)
                output.append(item)
            return output

        setattr(_preliminary_entries, _ENTRIES_MARKER, True)
        setattr(_preliminary_entries, "_nico_previous", current_entries)
        manifest._preliminary_entries = _preliminary_entries

    current_attach = manifest.attach_artifact_manifest
    if not getattr(current_attach, _ATTACH_MARKER, False):

        @wraps(current_attach)
        def attach_artifact_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
            result = current_attach(package)
            _validate_exact_artifact_hashes(result)
            completion = deepcopy(dict(result.get("client_report_completion") or {}))
            completion.update(
                {
                    "exact_artifact_hash_binding_version": VERSION,
                    "all_manifest_hashes_recomputed_from_final_bytes": True,
                    "all_manifest_byte_sizes_recomputed_from_final_bytes": True,
                    "markdown_manifest_hash_matches_final_bytes": True,
                    "html_manifest_hash_matches_final_bytes": True,
                    "detached_manifest_hash_matches_final_bytes": True,
                }
            )
            result["client_report_completion"] = completion
            return result

        setattr(attach_artifact_manifest, _ATTACH_MARKER, True)
        setattr(attach_artifact_manifest, "_nico_previous", current_attach)
        manifest.attach_artifact_manifest = attach_artifact_manifest

    return {
        "status": "installed",
        "version": VERSION,
        "all_manifest_hashes_recomputed_from_final_bytes": True,
        "all_manifest_byte_sizes_recomputed_from_final_bytes": True,
        "markdown_manifest_hash_matches_final_bytes": True,
        "html_manifest_hash_matches_final_bytes": True,
        "detached_manifest_hash_matches_final_bytes": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_exact_artifact_hash_binding_v1",
]
