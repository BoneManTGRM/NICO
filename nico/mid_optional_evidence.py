from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from nico.mid_assessment_runs import load_mid_assessment_run
from nico.storage import STORE, StorageAdapter

ACCESS_PREFIX = "mid_evidence_access"
EVIDENCE_PREFIX = "mid_optional_evidence"
TOKEN_PREFIX = "midevidence"
TOKEN_LIFETIME_HOURS = 168
MAX_FIELD_CHARS = 20_000
MAX_TOTAL_CHARS = 100_000

OPTIONAL_EVIDENCE_FIELDS = {
    "application_url": "Application or staging URL",
    "ios_build_access": "iOS build access or instructions",
    "android_build_access": "Android build access or instructions",
    "architecture_documents": "Architecture documents or bounded summary",
    "product_requirements": "Product requirements or bounded summary",
    "stakeholder_questionnaire": "Stakeholder questionnaire responses",
    "meeting_transcripts": "Meeting transcript excerpts or bounded summary",
    "existing_roadmap": "Existing roadmap or bounded summary",
    "business_priorities": "Business priorities, constraints, budget, and goals",
}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_id(prefix: str, run_id: str) -> str:
    return f"{prefix}_{hashlib.sha256(run_id.encode()).hexdigest()[:20]}"


def _run_identity(run_id: str, store: StorageAdapter) -> dict[str, Any] | None:
    record = load_mid_assessment_run(run_id, store=store)
    if not record:
        return None
    snapshot_id = str(record.get("snapshot_id") or "")
    snapshot_sha = str(record.get("snapshot_commit_sha") or "")
    if not snapshot_id or len(snapshot_sha) < 40:
        return None
    return {
        "run_id": run_id,
        "customer_id": str(record.get("customer_id") or "default_customer"),
        "project_id": str(record.get("project_id") or "default_project"),
        "repository": str(record.get("repository") or ""),
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot_sha,
    }


def issue_mid_evidence_submission_access(run_id: str, store: StorageAdapter | None = None) -> dict[str, Any]:
    """Issue a one-time-returned capability bound to one persisted Mid snapshot."""

    active = _store(store)
    identity = _run_identity(str(run_id or ""), active)
    if not identity:
        return {
            "status": "unavailable",
            "message": "Optional evidence submission is unavailable until the Mid run and exact repository snapshot are durably recorded.",
        }
    access_id = _record_id(ACCESS_PREFIX, identity["run_id"])
    existing = active.get("evidence_items", access_id)
    if existing:
        return {
            "status": "already_issued",
            "access_id": access_id,
            "expires_at": existing.get("expires_at") or "",
            "message": "The optional-evidence submission capability was already issued and is not returned again.",
        }

    raw_token = f"{TOKEN_PREFIX}.{access_id}.{secrets.token_urlsafe(32)}"
    issued_at = _now()
    expires_at = issued_at + timedelta(hours=TOKEN_LIFETIME_HOURS)
    record = {
        "evidence_id": access_id,
        **identity,
        "record_type": "mid_optional_evidence_access",
        "status": "active",
        "token_hash": _sha256(raw_token),
        "token_fingerprint": _sha256(raw_token)[:12],
        "issued_at": _iso(issued_at),
        "expires_at": _iso(expires_at),
        "allowed_fields": sorted(OPTIONAL_EVIDENCE_FIELDS),
        "raw_token_stored": False,
        "source": "mid_optional_evidence_access",
        "filename": "mid-optional-evidence-access.json",
        "content_type": "application/json",
        "size_bytes": 0,
    }
    active.put("evidence_items", access_id, record)
    active.audit(
        "mid.optional_evidence_access_issued",
        {
            "access_id": access_id,
            "run_id": identity["run_id"],
            "snapshot_id": identity["snapshot_id"],
            "snapshot_commit_sha": identity["snapshot_commit_sha"],
            "expires_at": record["expires_at"],
            "token_fingerprint": record["token_fingerprint"],
        },
        customer_id=identity["customer_id"],
        project_id=identity["project_id"],
    )
    return {
        "status": "issued",
        "access_id": access_id,
        "token": raw_token,
        "expires_at": record["expires_at"],
        "allowed_fields": record["allowed_fields"],
        "warning": "The submission token is returned once. NICO stores only its SHA-256 hash and short fingerprint.",
    }


def _validated_fields(payload: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    errors: list[str] = []
    total = 0
    for key in OPTIONAL_EVIDENCE_FIELDS:
        raw = payload.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        if len(value) > MAX_FIELD_CHARS:
            errors.append(f"{key} exceeds the {MAX_FIELD_CHARS}-character limit.")
            continue
        total += len(value)
        fields[key] = value
    if total > MAX_TOTAL_CHARS:
        errors.append(f"Optional evidence exceeds the {MAX_TOTAL_CHARS}-character total limit.")
    application_url = fields.get("application_url")
    if application_url:
        parsed = urlparse(application_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("application_url must be an absolute http or https URL.")
    return fields, errors


def _availability(fields: dict[str, str]) -> dict[str, dict[str, Any]]:
    def section(name: str, keys: list[str], requirement: str) -> dict[str, Any]:
        supplied = [key for key in keys if fields.get(key)]
        return {
            "section": name,
            "status": "human_review_required" if supplied else "unavailable",
            "submitted_fields": supplied,
            "direct_repository_proof": False,
            "message": (
                "User-submitted context is available and requires validation before any conclusion or score change."
                if supplied
                else requirement
            ),
        }

    return {
        "functional_qa": section(
            "Functional QA",
            ["application_url", "ios_build_access", "android_build_access", "product_requirements"],
            "Unavailable: functional QA requires a functioning application, build, test environment, or equivalent direct evidence.",
        ),
        "platform_parity": section(
            "Platform parity",
            ["ios_build_access", "android_build_access", "product_requirements"],
            "Unavailable: platform parity requires access to the relevant platform builds and expected behavior.",
        ),
        "architecture_context": section(
            "Architecture context",
            ["architecture_documents", "product_requirements"],
            "Unavailable: no external architecture or product context was submitted.",
        ),
        "stakeholder_alignment": section(
            "Stakeholder alignment",
            ["stakeholder_questionnaire", "meeting_transcripts", "business_priorities"],
            "Unavailable: stakeholder conclusions require questionnaires, interviews, transcripts, or equivalent notes.",
        ),
        "business_roadmap": section(
            "Business-aligned roadmap",
            ["existing_roadmap", "business_priorities", "product_requirements", "stakeholder_questionnaire"],
            "Unavailable: a business-aligned roadmap requires goals, priorities, constraints, and product context.",
        ),
    }


def optional_evidence_summary(run_id: str, store: StorageAdapter | None = None) -> dict[str, Any]:
    active = _store(store)
    identity = _run_identity(str(run_id or ""), active)
    if not identity:
        return {"status": "unavailable", "run_id": run_id, "fields_submitted": [], "section_availability": _availability({})}
    evidence_id = _record_id(EVIDENCE_PREFIX, identity["run_id"])
    record = active.get("evidence_items", evidence_id)
    fields = record.get("submitted_evidence") if isinstance(record, dict) and isinstance(record.get("submitted_evidence"), dict) else {}
    return {
        "status": "submitted" if fields else "not_submitted",
        "evidence_id": evidence_id if record else "",
        **identity,
        "fields_submitted": sorted(fields),
        "field_count": len(fields),
        "section_availability": _availability(fields),
        "submitted_at": record.get("submitted_at") if record else "",
        "updated_at": record.get("updated_at") if record else "",
        "source_classification": "user_submitted_external_context",
        "verification_status": "human_review_required" if fields else "unavailable",
        "direct_repository_proof": False,
        "score_change_allowed_without_review": False,
        "retention_note": "Submitted context is retained with the Mid run scope. It is not repository proof and must be reviewed before use in findings or scoring.",
    }


def submit_mid_optional_evidence(run_id: str, payload: dict[str, Any], store: StorageAdapter | None = None) -> dict[str, Any]:
    active = _store(store)
    identity = _run_identity(str(run_id or ""), active)
    if not identity:
        return {"status": "not_found", "error": "Mid Assessment run or snapshot not found."}
    token = str(payload.get("token") or "").strip()
    access_id = _record_id(ACCESS_PREFIX, identity["run_id"])
    access = active.get("evidence_items", access_id)
    expires_at = _parse_iso(access.get("expires_at")) if isinstance(access, dict) else None
    valid = bool(
        access
        and access.get("status") == "active"
        and access.get("run_id") == identity["run_id"]
        and access.get("snapshot_id") == identity["snapshot_id"]
        and access.get("snapshot_commit_sha") == identity["snapshot_commit_sha"]
        and expires_at
        and expires_at > _now()
        and token
        and hmac.compare_digest(str(access.get("token_hash") or ""), _sha256(token))
    )
    if not valid:
        return {"status": "not_found", "error": "Optional evidence submission is unavailable."}

    fields, errors = _validated_fields(payload)
    if errors:
        return {"status": "blocked", "error": " ".join(errors)}
    if not fields:
        return {"status": "blocked", "error": "At least one optional evidence field is required."}

    evidence_id = _record_id(EVIDENCE_PREFIX, identity["run_id"])
    existing = active.get("evidence_items", evidence_id) or {}
    merged = dict(existing.get("submitted_evidence") or {})
    merged.update(fields)
    submitted_at = existing.get("submitted_at") or _iso(_now())
    record = {
        "evidence_id": evidence_id,
        **identity,
        "record_type": "mid_optional_evidence",
        "status": "submitted",
        "submitted_evidence": merged,
        "fields_submitted": sorted(merged),
        "source": "user_submitted_external_context",
        "source_classification": "user_submitted_external_context",
        "verification_status": "human_review_required",
        "direct_repository_proof": False,
        "score_change_allowed_without_review": False,
        "submitted_at": submitted_at,
        "last_submission_at": _iso(_now()),
        "filename": "mid-optional-evidence.json",
        "content_type": "application/json",
        "size_bytes": sum(len(value) for value in merged.values()),
        "retention_note": "This context is retained for human review and is never treated as direct repository proof.",
    }
    active.put("evidence_items", evidence_id, record)
    active.audit(
        "mid.optional_evidence_submitted",
        {
            "evidence_id": evidence_id,
            "run_id": identity["run_id"],
            "snapshot_id": identity["snapshot_id"],
            "snapshot_commit_sha": identity["snapshot_commit_sha"],
            "fields_submitted": sorted(fields),
            "field_count": len(fields),
            "token_fingerprint": access.get("token_fingerprint") or "",
            "direct_repository_proof": False,
        },
        customer_id=identity["customer_id"],
        project_id=identity["project_id"],
    )
    return {
        "status": "submitted",
        "idempotent_update": bool(existing),
        "optional_evidence": optional_evidence_summary(identity["run_id"], store=active),
    }
