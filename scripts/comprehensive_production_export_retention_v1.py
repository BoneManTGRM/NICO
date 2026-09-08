"""Retain downloaded production bytes; never generate replacement report artifacts.

The proof credential permits the existing full-status and four report routes.
The full-status response contains the stored artifact family and detached manifest.
The localized route exposes Markdown and PDF only: this collector records that
remaining bilingual export gap, rather than inventing a JSON/HTML export route.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from nico.comprehensive_api_controller import _retained_manifest_integrity_bound
from nico.comprehensive_exact_artifact_hash_binding_v1 import (
    _artifact_bytes,
    _validate_exact_artifact_hashes,
)

SCHEMA = "nico.production-export-download-receipt.v1"
_ACTIVE: ContextVar["Capture | None"] = ContextVar("nico_export_capture", default=None)
_SAFE_NAME = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
_HEADERS = {
    "content-type", "content-length", "content-disposition", "etag",
    "x-nico-run-id", "x-nico-commit-sha", "x-nico-report-id",
    "x-nico-report-language", "x-nico-artifact-sha256", "x-nico-pdf-sha256",
    "x-nico-canonical-truth-sha256", "x-nico-assessment-rerun",
    "x-nico-human-review-required", "x-nico-human-review-completed",
    "x-nico-approval-status", "x-nico-delivery-status",
    "x-nico-client-delivery-allowed", "x-nico-localized-artifact-requires-new-approval",
    "x-nico-frozen-source-artifact",
}


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class Capture:
    def __init__(self, run_id: str, commit_sha: str) -> None:
        _require(_SAFE_NAME.fullmatch(run_id), "unsafe export receipt run identifier")
        parent = Path("audit-results/export-retention") / run_id
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="capture-", dir=parent))
        self.receipt: dict[str, Any] = {
            "artifact_schema": SCHEMA,
            "run_id": run_id,
            "assessed_commit_sha": commit_sha,
            "status": "IN_PROGRESS",
            "files": [],
            "full_bilingual_export_acceptance": False,
            "professional_review_or_delivery_approval": False,
            "collector_workflow": {
                "source_sha": os.getenv("GITHUB_SHA") or None,
                "run_id": os.getenv("GITHUB_RUN_ID") or None,
                "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT") or None,
                "is_nico_deployment_identity": False,
            },
        }

    def retain(self, label: str, content: bytes, **metadata: Any) -> dict[str, Any]:
        _require(_SAFE_NAME.fullmatch(label), "unsafe export receipt artifact label")
        suffix = ".json"
        if "pdf" in label:
            suffix = ".pdf"
        elif "html" in label:
            suffix = ".html"
        elif "markdown" in label and "envelope" not in label:
            suffix = ".md"
        elif label.endswith("csv"):
            suffix = ".csv"
        filename = f"{len(self.receipt['files']) + 1:03d}-{label}{suffix}"
        path = self.directory / filename
        with path.open("xb") as output:
            output.write(content)
        item = {
            "label": label, "path": filename, "size_bytes": len(content),
            "sha256": _sha(content), **metadata,
        }
        self.receipt["files"].append(item)
        return item

    def finish(self) -> None:
        expected = {
            "canonical-json": 2, "terminal-status-before": 1,
            "terminal-status-after": 1, "localized-pdf-en": 1,
            "localized-pdf-es-MX": 1, "retained-family-response": 1,
            "source-markdown": 1, "source-html": 1, "source-pdf": 1,
            "localized-markdown-envelope-en": 1,
            "localized-markdown-envelope-es-MX": 1,
        }
        for label, count in expected.items():
            _require(sum(item["label"] == label for item in self.receipt["files"]) == count,
                     f"required production download missing or duplicated: {label}")
        for item in self.receipt["files"]:
            content = (self.directory / item["path"]).read_bytes()
            _require(len(content) == item["size_bytes"] and _sha(content) == item["sha256"],
                     f"retained production download changed: {item['label']}")
        _require(self.receipt.get("supported_export_bindings_verified") is True,
                 "supported export bindings were not verified")
        bindings = self.receipt["bindings"]
        for item in self.receipt["files"]:
            if not item["label"].startswith("localized-pdf-"):
                continue
            headers = item["response_headers"]
            for key, value in {
                "x-nico-run-id": self.receipt["run_id"],
                "x-nico-commit-sha": self.receipt["assessed_commit_sha"],
                "x-nico-canonical-truth-sha256": bindings["canonical_truth_sha256"],
                "x-nico-artifact-sha256": item["sha256"],
                "x-nico-approval-status": "pending_human_approval",
                "x-nico-delivery-status": "blocked_pending_human_approval",
                "x-nico-client-delivery-allowed": "false",
            }.items():
                _require(headers.get(key) == value, f"localized PDF declared binding mismatch: {key}")
            if headers.get("x-nico-frozen-source-artifact") == "true":
                _require(item["sha256"] == bindings["draft_artifact_identity"]["pdf_sha256"],
                         "frozen localized PDF differs from retained source artifact")
        self.receipt["status"] = "VERIFIED_SUPPORTED_EXPORTS_WITH_GAPS"

    def write_receipt(self) -> Path:
        path = self.directory / "download-manifest.json"
        path.write_text(json.dumps(self.receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return path


def capture_terminal_exports(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Make byte retention/integrity mandatory at the actual release entrypoint."""
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        capture = Capture(kwargs["run_id"], kwargs["expected_commit_sha"])
        token = _ACTIVE.set(capture)
        try:
            result = function(*args, **kwargs)
            capture.finish()
            path = capture.write_receipt()
            return {
                **result,
                "export_download_manifest_path": path.as_posix(),
                "export_download_manifest_sha256": _sha(path.read_bytes()),
                "supported_export_bytes_and_bindings_verified": True,
                "full_bilingual_export_acceptance": False,
                "export_acceptance_gaps": capture.receipt["gaps"],
            }
        except Exception as exc:
            capture.receipt["status"] = "FAILED"
            # Error class is sufficient; do not duplicate private payloads or secrets.
            capture.receipt["failure_type"] = type(exc).__name__
            capture.write_receipt()
            raise
        finally:
            _ACTIVE.reset(token)
    return wrapped


def retain_response(label: str, *, route: str, status: int, headers: Any, content: bytes) -> None:
    capture = _ACTIVE.get()
    if capture is not None:
        safe_headers = {str(k).lower(): str(v) for k, v in headers.items()
                        if str(k).lower() in _HEADERS}
        capture.retain(label, content, route=route, http_status=status,
                       response_headers=safe_headers, origin="production_http_response")


def collect_supported_exports(
    fetch: Callable[[str], Any], *, run_id: str, commit_sha: str,
    canonical: dict[str, Any], terminal: dict[str, Any],
    terminal_snapshot: Callable[[dict[str, Any]], dict[str, Any]],
    require_pending: Callable[..., dict[str, Any]],
) -> None:
    capture = _ACTIVE.get()
    _require(capture is not None, "production export collection requires active entrypoint capture")
    assert capture is not None
    root = f"/api/nico/assessment/comprehensive-run/{run_id}"

    def download(suffix: str, label: str) -> tuple[bytes, dict[str, str]]:
        response = fetch(root + suffix)
        body = response.content
        retain_response(label, route=root + suffix, status=response.status_code,
                        headers=response.headers, content=body)
        _require(response.status_code == 200, f"production export HTTP failure: {label}")
        return body, {str(k).lower(): str(v) for k, v in response.headers.items()}

    # The supported full-status response contains the exact stored family. No
    # evidence-package route or broader proof credential is needed or requested.
    body, _headers = download("", "retained-family-response")
    full = json.loads(body)
    _require(isinstance(full, dict), "retained family status must be an object")
    _require(terminal_snapshot(full) == terminal_snapshot(terminal),
             "retained family does not match immutable terminal revision")
    require_pending(full, boundary="retained_export_family")
    report = full.get("reports")
    _require(isinstance(report, dict), "retained report family missing")
    _require(report.get("json") == canonical, "retained canonical JSON differs from actual JSON download")
    _require(all(report.get(key) not in (None, "") for key in (
        "report_id", "artifact_manifest", "evidence_manifest_json",
        "evidence_manifest_sha256", "canonical_json", "canonical_json_sha256",
        "draft_artifact_identity",
    )), "complete retained artifact manifest family required")
    _validate_exact_artifact_hashes(report)
    _require(_retained_manifest_integrity_bound(report), "retained manifest identity or hash binding invalid")
    identity = canonical.get("identity", {})
    _require(identity.get("run_id") == run_id and identity.get("commit_sha") == commit_sha,
             "retained canonical source/run mismatch")
    report_id = report["report_id"]
    _require(report_id == terminal["reports"].get("report_id"), "retained report identity differs from terminal")
    language = identity.get("report_language") or canonical.get("report_language")
    _require(language in ("en", "es-MX"), "retained report language missing")
    canonical_digest = report.get("canonical_truth_sha256")
    _require(canonical_digest == terminal["reports"].get("canonical_truth_sha256"),
             "retained canonical truth digest differs from terminal")
    entries = {item["artifact_type"]: item for item in report["artifact_manifest"]["artifacts"]}
    for artifact_type, item in entries.items():
        capture.retain("retained-" + artifact_type.replace("_", "-"), _artifact_bytes(report, artifact_type),
                       origin="exact_decoded_field_in_retained-family-response", declared_artifact=item)
    capture.retain("retained-evidence-manifest", report["evidence_manifest_json"].encode("utf-8"),
                   origin="exact_decoded_field_in_retained-family-response",
                   declared_sha256=report["evidence_manifest_sha256"])
    capture.receipt["bindings"] = {
        "canonical_identity": identity,
        "source_report_id": report_id,
        "terminal_snapshot": terminal_snapshot(terminal),
        "canonical_truth_sha256": canonical_digest,
        "draft_artifact_identity": report["draft_artifact_identity"],
        "manifest_identity": report["artifact_manifest"]["identity"],
        "manifest_approval": report["artifact_manifest"]["approval"],
        "manifest_lifecycle": report["artifact_manifest"]["lifecycle"],
        "undeclared_bindings_are_not_inferred": True,
    }

    def source_headers(headers: dict[str, str], content: bytes) -> None:
        expected = {
            "x-nico-run-id": run_id, "x-nico-commit-sha": commit_sha,
            "x-nico-report-id": report_id, "x-nico-report-language": language,
            "x-nico-canonical-truth-sha256": canonical_digest,
            "x-nico-artifact-sha256": _sha(content),
            "x-nico-assessment-rerun": "false",
            "x-nico-human-review-required": "true",
            "x-nico-human-review-completed": "false",
            "x-nico-client-delivery-allowed": "false",
            "x-nico-approval-status": "pending_human_approval",
            "x-nico-delivery-status": "blocked_pending_human_approval",
        }
        for key, value in expected.items():
            _require(headers.get(key) == value, f"production source export header mismatch: {key}")

    for route_format, artifact_type in (
        ("markdown", "markdown_report"), ("html", "html_report"), ("pdf", "comprehensive_pdf"),
    ):
        content, headers = download("/report/" + route_format, "source-" + route_format)
        source_headers(headers, content)
        _require(content == _artifact_bytes(report, artifact_type),
                 f"actual {route_format} download differs from exact retained manifest bytes")

    for locale in ("en", "es-MX"):
        content, _headers = download("/localized-report/" + locale, "localized-markdown-envelope-" + locale)
        localized = json.loads(content)
        _require(isinstance(localized, dict), "localized report envelope missing")
        for key, value in {
            "run_id": run_id, "commit_sha": commit_sha,
            "repository": identity.get("repository"),
            "evidence_ledger_id": identity.get("evidence_ledger_id"),
            "source_report_id": report_id, "source_report_language": language,
            "report_language": locale, "canonical_truth_sha256": canonical_digest,
            "source_integrity_sha256": terminal.get("integrity_sha256") or "",
            "same_canonical_run": True, "assessment_rerun": False,
            "canonical_truth_preserved": True, "approval_state_mutated": False,
            "delivery_state_mutated": False,
        }.items():
            _require(localized.get(key) == value, f"localized export identity/state mismatch: {key}")
        translated = localized.get("report", {})
        for lifecycle in (localized, localized.get("canonical_run_lifecycle", {}),
                          localized.get("localized_artifact_lifecycle", {}), translated):
            for key, value in {
                "human_review_required": True, "human_review_completed": False,
                "client_delivery_allowed": False, "approval_status": "pending_human_approval",
                "delivery_status": "blocked_pending_human_approval",
                "human_review_status": "pending", "client_delivery_status": "blocked",
            }.items():
                _require(lifecycle.get(key) == value, f"localized draft lifecycle mismatch: {key}")
        _require(translated.get("report_id") == report_id
                 and translated.get("presentation_language") == locale
                 and translated.get("canonical_truth_sha256") == canonical_digest,
                 "localized Markdown report binding mismatch")
        markdown = translated.get("markdown")
        _require(isinstance(markdown, str) and markdown, "localized Markdown bytes missing")
        markdown_bytes = markdown.encode("utf-8")
        capture.retain("localized-markdown-" + locale, markdown_bytes,
                       origin="exact_decoded_field_in_localized-markdown-envelope-" + locale,
                       declared_sha256=translated.get("markdown_sha256"))
        _require(_sha(markdown_bytes) == translated.get("markdown_sha256"),
                 "localized Markdown byte hash mismatch")
        scope = localized.get("artifact_scope")
        _require(scope in ("retained-canonical-artifact", "client-facing-same-run-projection"),
                 "localized Markdown artifact scope missing")
        if scope == "retained-canonical-artifact":
            _require(markdown_bytes == _artifact_bytes(report, "markdown_report"),
                     "localized retained Markdown differs from source bytes")
    alternate = "en" if language == "es-MX" else "es-MX"
    capture.receipt["gaps"] = [{
        "status": "BLOCKED_BY_HARD_GATE",
        "report_language": alternate,
        "formats": ["canonical_json", "html", "artifact_manifest", "evidence_manifest_json"],
        "reason": "Existing localized-report route exposes Markdown and PDF only; no alternate-language artifact-family download is installed.",
    }]
    capture.receipt["format_hash_policy"] = "Each exact byte stream has its own SHA-256; canonical JSON semantic digest is distinct from transport-byte digest. Localized projections may have different bytes."
    capture.receipt["supported_export_bindings_verified"] = True
