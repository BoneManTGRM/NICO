from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_authorized_report_v1 import (
    authorized_text,
    build_authorized_report_pdf,
)
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity,
    report_package_from_record,
)

VERSION = "nico.comprehensive_automated_delivery.v1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _entry_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return _json_bytes(value)


def build_automated_delivery_package(
    record: Mapping[str, Any],
    *,
    expected_artifact_identity: Mapping[str, Any],
    authorized_at: str | None = None,
) -> dict[str, Any]:
    if record.get("terminal") is not True or str(record.get("status") or "") != "review_required":
        raise ValueError("automated_delivery_requires_terminal_review_boundary")
    if record.get("human_review_completed") is True or record.get("client_delivery_allowed") is True:
        raise ValueError("automated_delivery_requires_unreleased_source_report")
    exact_identity = assert_expected_review_artifact_identity(
        record,
        expected_artifact_identity,
    )
    package = report_package_from_record(record)
    try:
        source_pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception as exc:
        raise ValueError("automated_delivery_source_pdf_invalid") from exc
    if not source_pdf.startswith(b"%PDF"):
        raise ValueError("automated_delivery_source_pdf_invalid")

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    timestamp = str(
        authorized_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    ).strip()
    source_pdf_sha = _sha256(source_pdf)
    authorization = {
        "artifact_schema": VERSION,
        "authorization_mode": "automated_policy",
        "status": "authorized",
        "human_reviewed": False,
        "security_certification": False,
        "authorizer_identity": "SARA",
        "authorizer_role": "Automated technical assessment and delivery system",
        "authorized_at": timestamp,
        "authorization_reason": (
            "Exact artifact passed independent logical verification, deterministic compilation, "
            "immutable identity validation, and the zero-unresolved-review-work gate."
        ),
        "source_report_artifact_digest": exact_identity["report_artifact_digest"],
        "source_pdf_sha256": source_pdf_sha,
        "run_id": str(identity.get("run_id") or ""),
        "repository": str(identity.get("repository") or ""),
        "commit_sha": str(identity.get("commit_sha") or ""),
    }
    authorization["authorization_sha256"] = _sha256(_json_bytes(authorization))
    authorized_pdf = build_authorized_report_pdf(
        source_pdf,
        identity=identity,
        delivery_authorization=authorization,
        source_pdf_sha256=source_pdf_sha,
        authorization_mode="automated",
    )

    canonical_json = (
        deepcopy(dict(package.get("json")))
        if isinstance(package.get("json"), Mapping)
        else {}
    )
    canonical_json["authorized_delivery"] = deepcopy(authorization)
    canonical_json["human_review_required"] = False
    canonical_json["human_review_completed"] = False
    canonical_json["client_delivery_allowed"] = True
    canonical_json["client_facing_status"] = "authorized_automated_technical_assessment"

    entries = {
        "01_nico_comprehensive_report.pdf": authorized_pdf,
        "02_nico_comprehensive_report.json": _json_bytes(canonical_json),
        "03_nico_comprehensive_report.md": _entry_bytes(
            authorized_text(str(package.get("markdown") or ""), authorization_mode="automated")
        ),
        "04_nico_comprehensive_report.html": _entry_bytes(
            authorized_text(str(package.get("html") or ""), authorization_mode="automated")
        ),
        "05_findings.csv": _entry_bytes(package.get("findings_csv") or ""),
        "06_evidence.csv": _entry_bytes(package.get("evidence_csv") or ""),
        "07_automated_authorization.json": _json_bytes(authorization),
    }
    manifest = {
        "artifact_schema": VERSION,
        "status": "authorized",
        "client_facing_status": "authorized_automated_technical_assessment",
        "authorization_mode": "automated_policy",
        "human_reviewed": False,
        "human_review_required": False,
        "client_delivery_allowed": True,
        "source_report_artifact_digest": exact_identity["report_artifact_digest"],
        "artifacts": [
            {"path": path, "sha256": _sha256(content), "size_bytes": len(content)}
            for path, content in sorted(entries.items())
        ],
    }
    entries["08_manifest.json"] = _json_bytes(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(entries.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    payload = buffer.getvalue()
    return {
        "artifact_schema": VERSION,
        "status": "authorized",
        "client_facing_status": "authorized_automated_technical_assessment",
        "authorization_mode": "automated_policy",
        "human_reviewed": False,
        "human_review_required": False,
        "client_delivery_allowed": True,
        "filename": f"nico-comprehensive-{identity.get('run_id')}-AUTHORIZED-AUTOMATED.zip",
        "zip_base64": base64.b64encode(payload).decode("ascii"),
        "zip_sha256": _sha256(payload),
        "zip_size_bytes": len(payload),
        "artifact_count": len(entries),
        "authorization": authorization,
        "manifest": manifest,
    }


__all__ = ["VERSION", "build_automated_delivery_package"]
