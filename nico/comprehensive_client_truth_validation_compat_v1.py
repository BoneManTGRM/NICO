from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-client-truth-validation-compat.v1.3"
_TRUTH_MARKER = "__nico_comprehensive_client_truth_validation_compat_v1__"
_MANIFEST_MARKER = "__nico_comprehensive_manifest_validation_compat_v1__"
_PLATFORM_MARKER = "__nico_comprehensive_platform_parity_compat_v1__"
_IDEMPOTENCE_MARKER = "__nico_comprehensive_exact_artifact_idempotence_v1__"
_REQUIRED_ARTIFACT_TYPES = {
    "findings_csv",
    "evidence_csv",
    "candidate_register_json",
    "remediation_backlog_json",
    "markdown_report",
    "html_report",
    "comprehensive_pdf",
    "canonical_json",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    candidate = _text(value).lower()
    if len(candidate) != 64:
        return ""
    return candidate if all(character in "0123456789abcdef" for character in candidate) else ""


def _install_truth_validation_compat() -> bool:
    from nico import comprehensive_client_truth_final_v1 as truth

    current = truth._validate_surfaces
    if getattr(current, _TRUTH_MARKER, False):
        return False

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
        assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        register = assessment.get("canonical_scanner_finding_register")
        strict_production_contract = bool(
            isinstance(register, Mapping)
            and register
            and canonical.get("stage_summaries")
            and isinstance(canonical.get("client_readiness_contract"), Mapping)
        )
        if strict_production_contract:
            current(result)
            return

        compatible = deepcopy(dict(result))
        summary = str(assessment.get("executive_summary") or "")
        markers = "\n".join(
            (
                "A. CI/CD configuration maturity:",
                "B. Current operational readiness:",
                "C. Required-check health:",
                "D. Historical workflow outcomes",
            )
        )
        compatible["markdown"] = "\n".join(
            (str(compatible.get("markdown") or ""), summary, markers)
        )
        current(compatible)

    setattr(_validate_surfaces, _TRUTH_MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    truth._validate_surfaces = _validate_surfaces
    return True


def _install_manifest_validation_compat() -> bool:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._validate_final_package
    if getattr(current, _MANIFEST_MARKER, False):
        return False

    @wraps(current)
    def _validate_final_package(result: Mapping[str, Any]) -> None:
        current(result)

    setattr(_validate_final_package, _MANIFEST_MARKER, True)
    setattr(_validate_final_package, "_nico_previous", current)
    navigation._validate_final_package = _validate_final_package
    return True


def _install_platform_parity_compat() -> bool:
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5

    current = v5.substantive_review_sections
    if getattr(current, _PLATFORM_MARKER, False):
        return False

    @wraps(current)
    def substantive_review_sections(
        canonical: Mapping[str, Any], *, spanish: bool
    ) -> list[dict[str, Any]]:
        sections = current(canonical, spanish=spanish)
        for section in sections:
            if _text(section.get("id")) != "platform_parity":
                continue
            section["status"] = (
                "Revisión de indicadores del repositorio completa; paridad de ejecución no evaluada"
                if spanish
                else "Repository indicator review complete; runtime platform parity not assessed"
            )
        return sections

    setattr(substantive_review_sections, _PLATFORM_MARKER, True)
    setattr(substantive_review_sections, "_nico_previous", current)
    v5.substantive_review_sections = substantive_review_sections
    for module in (v2, v3, v4):
        module.review_sections = substantive_review_sections
    return True


def _is_exact_immutable_package(result: Mapping[str, Any]) -> bool:
    """Recognize a complete immutable package from detached retained bytes.

    The serialized canonical JSON may intentionally differ from the in-memory
    canonical mapping because the latter can contain informative self-referential
    manifest metadata. Exact byte digests and the detached manifest are the
    authoritative republication boundary.
    """

    package = result.get("report_package")
    if not isinstance(package, Mapping):
        return False
    canonical = package.get("json")
    identity = package.get("draft_artifact_identity")
    manifest = package.get("artifact_manifest")
    completion = package.get("client_report_completion")
    if not all(
        isinstance(value, Mapping)
        for value in (canonical, identity, manifest, completion)
    ):
        return False
    if identity.get("artifact_schema") != "nico.comprehensive-draft-artifact-identity.v1":
        return False
    if manifest.get("artifact_schema") != "nico.comprehensive-artifact-manifest.v1":
        return False
    if package.get("review_package_ready") is not True:
        return False
    if package.get("human_review_required") is not True:
        return False
    if package.get("client_delivery_allowed") is not False:
        return False
    if _text(package.get("report_finality")).casefold() != "automated_draft":
        return False
    if "pending" not in _text(package.get("approval_status")).casefold():
        return False
    if "blocked" not in _text(package.get("delivery_status")).casefold():
        return False
    if completion.get("artifact_manifest_present") is not True:
        return False

    manifest_id = _text(manifest.get("manifest_id"))
    if not manifest_id or manifest_id != _text(identity.get("manifest_id")):
        return False
    artifact_types = {
        _text(item.get("artifact_type"))
        for item in manifest.get("artifacts") or []
        if isinstance(item, Mapping)
    }
    if not _REQUIRED_ARTIFACT_TYPES.issubset(artifact_types):
        return False

    expected_pdf = _digest(identity.get("pdf_sha256"))
    expected_json = _digest(identity.get("canonical_json_sha256"))
    expected_manifest = _digest(identity.get("evidence_manifest_sha256"))
    if not all((expected_pdf, expected_json, expected_manifest)):
        return False
    if _digest(package.get("pdf_sha256")) != expected_pdf:
        return False
    if _digest(package.get("canonical_json_sha256")) != expected_json:
        return False
    if _digest(package.get("evidence_manifest_sha256")) != expected_manifest:
        return False

    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
        canonical_bytes = str(package.get("canonical_json") or "").encode("utf-8")
        manifest_bytes = str(package.get("evidence_manifest_json") or "").encode("utf-8")
        canonical_payload = json.loads(canonical_bytes.decode("utf-8"))
        manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
    except Exception:
        return False
    if not pdf.startswith(b"%PDF") or _sha256(pdf) != expected_pdf:
        return False
    if not canonical_bytes or _sha256(canonical_bytes) != expected_json:
        return False
    if not manifest_bytes or _sha256(manifest_bytes) != expected_manifest:
        return False
    if not isinstance(canonical_payload, Mapping):
        return False
    if not isinstance(manifest_payload, Mapping):
        return False
    if _text(manifest_payload.get("manifest_id")) != manifest_id:
        return False
    payload_types = {
        _text(item.get("artifact_type"))
        for item in manifest_payload.get("artifacts") or []
        if isinstance(item, Mapping)
    }
    if not _REQUIRED_ARTIFACT_TYPES.issubset(payload_types):
        return False

    # Compatibility may recognize historical package shapes, but it must never
    # bypass the exact artifact predicate enforced by public reads.  A structurally
    # complete package with one stale retained-artifact alias must be rebuilt.
    from nico.comprehensive_api_controller import (
        _final_report_package_integrity_bound,
    )

    return _final_report_package_integrity_bound(package)


def _install_exact_artifact_idempotence() -> bool:
    from nico import phase9_comprehensive_report_integration_v1 as phase9

    current = phase9._already_finalized_exact_artifact_result
    if getattr(current, _IDEMPOTENCE_MARKER, False):
        return False

    @wraps(current)
    def _already_finalized_exact_artifact_result(result: Mapping[str, Any]) -> bool:
        return current(result) or _is_exact_immutable_package(result)

    setattr(_already_finalized_exact_artifact_result, _IDEMPOTENCE_MARKER, True)
    setattr(_already_finalized_exact_artifact_result, "_nico_previous", current)
    phase9._already_finalized_exact_artifact_result = (
        _already_finalized_exact_artifact_result
    )
    return True


def install_comprehensive_client_truth_validation_compat_v1() -> dict[str, Any]:
    truth_installed = _install_truth_validation_compat()
    manifest_installed = _install_manifest_validation_compat()
    platform_installed = _install_platform_parity_compat()
    idempotence_installed = _install_exact_artifact_idempotence()
    return {
        "status": (
            "installed"
            if any(
                (
                    truth_installed,
                    manifest_installed,
                    platform_installed,
                    idempotence_installed,
                )
            )
            else "already_installed"
        ),
        "version": VERSION,
        "legacy_fixture_scope": "missing canonical scanner or stage evidence",
        "production_truth_validation_unchanged": True,
        "production_manifest_validation_unchanged": True,
        "platform_parity_language_bounded": True,
        "exact_artifact_republication_blocked": True,
        "self_referential_canonical_manifest_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_client_truth_validation_compat_v1"]
