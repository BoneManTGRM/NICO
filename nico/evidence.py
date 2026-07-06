from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from nico.storage import STORE

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "video/mp4",
}
TEXT_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_content_type(content_type: str | None) -> tuple[bool, str]:
    if not content_type:
        return False, "Missing content type."
    if content_type not in ALLOWED_CONTENT_TYPES:
        return False, f"Unsupported content type: {content_type}"
    return True, "ok"


async def upload_evidence(
    file: UploadFile,
    customer_id: str = "default_customer",
    project_id: str = "default_project",
    run_id: str = "",
) -> dict[str, Any]:
    ok, message = validate_content_type(file.content_type)
    if not ok:
        return {"status": "blocked", "error": message}
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return {"status": "blocked", "error": f"File exceeds max upload size of {MAX_UPLOAD_BYTES} bytes."}
    extracted_text = ""
    unavailable: list[str] = []
    if file.content_type in TEXT_TYPES:
        extracted_text = content.decode("utf-8", errors="replace")[:12000]
    elif file.content_type == "application/pdf":
        unavailable.append("PDF text extraction is not enabled in this safe MVP; file metadata is stored only.")
    else:
        unavailable.append("Binary media is stored as metadata only in this safe MVP; no conclusions are invented from unread media.")

    evidence_id = f"evidence_{uuid4().hex[:16]}"
    metadata = {
        "status": "complete",
        "evidence_id": evidence_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "run_id": run_id,
        "filename": file.filename or "upload",
        "content_type": file.content_type,
        "size_bytes": len(content),
        "extracted_text_preview": extracted_text,
        "unavailable_data_notes": unavailable,
        "created_at": now_iso(),
        "retention_note": "This MVP stores metadata and text preview only. Configure object storage before keeping private files.",
    }
    STORE.put("evidence_items", evidence_id, metadata)
    STORE.audit("evidence.uploaded", {"evidence_id": evidence_id, "filename": metadata["filename"]}, customer_id=customer_id, project_id=project_id)
    return metadata


def list_evidence(project_id: str, customer_id: str | None = None) -> list[dict[str, Any]]:
    return STORE.list("evidence_items", customer_id=customer_id, project_id=project_id)
