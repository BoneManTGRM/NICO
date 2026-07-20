from __future__ import annotations

import hashlib
import json
from typing import Any

VERSION = "nico.express_production_certification.v25"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _status(value: Any) -> str:
    return _text(value).casefold()


def _sha(value: Any) -> str:
    text = _text(value).casefold()
    return text if len(text) == 40 and all(ch in "0123456789abcdef" for ch in text) else ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _artifact_digest(result: dict[str, Any]) -> str:
    reports = _dict(result.get("reports"))
    payload = {
        "repository": _text(result.get("repository")),
        "assessed_commit_sha": _sha(
            result.get("commit_sha")
            or result.get("snapshot_sha")
            or result.get("assessed_commit_sha")
        ),
        "markdown": str(reports.get("markdown") or ""),
        "html": str(reports.get("html") or ""),
        "pdf_length": len(str(reports.get("pdf_base64") or "")),
        "truth_fingerprint": _text(_dict(result.get("express_cross_format_contract")).get("truth_fingerprint")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _deployment_gate(result: dict[str, Any], assessed_sha: str) -> dict[str, Any]:
    deployment = _dict(result.get("production_deployment"))
    provider_evidence = _dict(result.get("production_release_provider_evidence"))
    backend_sha = _sha(
        deployment.get("backend_sha")
        or deployment.get("railway_sha")
        or provider_evidence.get("backend_commit_sha")
    )
    frontend_sha = _sha(
        deployment.get("frontend_sha")
        or deployment.get("vercel_sha")
        or provider_evidence.get("frontend_commit_sha")
    )
    checks = {
        "assessed_sha_present": bool(assessed_sha),
        "backend_sha_present": bool(backend_sha),
        "frontend_sha_present": bool(frontend_sha),
        "backend_matches_assessed": bool(assessed_sha and backend_sha == assessed_sha),
        "frontend_matches_assessed": bool(assessed_sha and frontend_sha == assessed_sha),
    }
    return {
        "status": "complete" if all(checks.values()) else "degraded",
        "checks": checks,
        "assessed_sha": assessed_sha,
        "backend_sha": backend_sha,
        "frontend_sha": frontend_sha,
    }


def _restart_gate(result: dict[str, Any]) -> dict[str, Any]:
    proof = _dict(result.get("restart_retrieval_proof") or result.get("production_restart_proof"))
    before = _text(proof.get("before_restart_run_id"))
    after = _text(proof.get("after_restart_run_id"))
    checks = {
        "proof_present": bool(proof),
        "restart_executed": bool(proof.get("restart_executed")),
        "same_run_retrieved": bool(before and after and before == after),
        "artifact_digest_preserved": bool(proof.get("artifact_digest_preserved")),
        "storage_durable": bool(proof.get("storage_durable")),
    }
    return {
        "status": "complete" if all(checks.values()) else "degraded",
        "checks": checks,
        "run_id": after or before,
    }


def _repeatability_gate(result: dict[str, Any], assessed_sha: str) -> dict[str, Any]:
    runs = [item for item in _list(result.get("same_sha_verification_runs")) if isinstance(item, dict)]
    matching = [item for item in runs if _sha(item.get("commit_sha")) == assessed_sha and _status(item.get("status")) == "complete"]
    fingerprints = {_text(item.get("truth_fingerprint")) for item in matching if _text(item.get("truth_fingerprint"))}
    artifact_digests = {_text(item.get("artifact_digest")) for item in matching if _text(item.get("artifact_digest"))}
    checks = {
        "assessed_sha_present": bool(assessed_sha),
        "two_completed_runs": len(matching) >= 2,
        "same_truth_fingerprint": len(fingerprints) == 1 and bool(fingerprints),
        "same_artifact_digest": len(artifact_digests) == 1 and bool(artifact_digests),
    }
    return {
        "status": "complete" if all(checks.values()) else "degraded",
        "checks": checks,
        "matching_run_count": len(matching),
        "run_ids": [_text(item.get("run_id")) for item in matching],
    }


def _locale_gate(result: dict[str, Any]) -> dict[str, Any]:
    parity = _dict(result.get("express_locale_parity") or result.get("language_parity"))
    locales = {_status(item) for item in _list(parity.get("verified_locales"))}
    checks = {
        "parity_record_present": bool(parity),
        "english_verified": "en" in locales or "english" in locales,
        "spanish_verified": "es" in locales or "spanish" in locales,
        "section_count_equal": bool(parity.get("section_count_equal")),
        "score_status_equal": bool(parity.get("score_status_equal")),
        "artifact_formats_equal": bool(parity.get("artifact_formats_equal")),
    }
    return {
        "status": "complete" if all(checks.values()) else "degraded",
        "checks": checks,
        "verified_locales": sorted(locales),
    }


def _artifact_gate(result: dict[str, Any]) -> dict[str, Any]:
    reports = _dict(result.get("reports"))
    terminal = _dict(result.get("express_terminal_contract"))
    manifest = _dict(result.get("express_artifact_manifest"))
    digest = _artifact_digest(result)
    recorded_digest = _text(manifest.get("artifact_digest"))
    checks = {
        "terminal_contract_complete": _status(terminal.get("status")) == "complete",
        "pdf_present": bool(str(reports.get("pdf_base64") or "").strip()),
        "markdown_present": bool(str(reports.get("markdown") or "").strip()),
        "html_present": bool(str(reports.get("html") or "").strip()),
        "manifest_present": bool(manifest),
        "manifest_digest_matches": bool(recorded_digest and recorded_digest == digest),
    }
    return {
        "status": "complete" if all(checks.values()) else "degraded",
        "checks": checks,
        "computed_artifact_digest": digest,
        "recorded_artifact_digest": recorded_digest,
    }


def build_express_production_certification(result: dict[str, Any]) -> dict[str, Any]:
    assessed_sha = _sha(
        result.get("commit_sha")
        or result.get("snapshot_sha")
        or result.get("assessed_commit_sha")
    )
    gates = {
        "deployment_identity": _deployment_gate(result, assessed_sha),
        "restart_retrieval": _restart_gate(result),
        "same_sha_repeatability": _repeatability_gate(result, assessed_sha),
        "english_spanish_parity": _locale_gate(result),
        "artifact_manifest_integrity": _artifact_gate(result),
    }
    incomplete = [name for name, gate in gates.items() if gate.get("status") != "complete"]
    certification = {
        "status": "complete" if not incomplete else "degraded",
        "version": VERSION,
        "gates": gates,
        "incomplete_gates": incomplete,
        "verified_gate_count": len(gates) - len(incomplete),
        "required_gate_count": len(gates),
        "fail_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    result["express_production_certification"] = certification
    return certification


__all__ = ["VERSION", "build_express_production_certification"]
