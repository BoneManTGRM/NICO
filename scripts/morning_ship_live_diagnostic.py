#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ORIGIN = os.environ.get("NICO_PRODUCTION_FRONTEND_URL", "https://app.nicoaudit.com").rstrip("/")
RUN_ID = os.environ.get("NICO_DIAGNOSTIC_RUN_ID", "").strip()
OUTPUT = Path(os.environ.get("NICO_DIAGNOSTIC_OUTPUT", "audit-results/morning-ship-live-diagnostic.json"))


def fetch(path: str, accept: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        ORIGIN + path,
        headers={"Accept": accept, "Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return int(response.status), {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            return text
    return ""


def recursive_first(value: Any, key: str) -> str:
    if isinstance(value, dict):
        if key in value:
            direct = value.get(key)
            if isinstance(direct, list):
                for item in direct:
                    text = first_nonempty(item)
                    if text:
                        return text
            else:
                text = first_nonempty(direct)
                if text:
                    return text
        for nested in value.values():
            found = recursive_first(nested, key)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = recursive_first(nested, key)
            if found:
                return found
    return ""


def main() -> int:
    if not RUN_ID.startswith("comprun_"):
        raise SystemExit("NICO_DIAGNOSTIC_RUN_ID must be an exact comprun_ id")

    result: dict[str, Any] = {
        "artifact_schema": "nico.morning_ship_live_diagnostic.v1",
        "origin": ORIGIN,
        "run_id": RUN_ID,
    }

    status_code, status_headers, status_bytes = fetch(
        f"/api/nico/assessment/comprehensive-run/{RUN_ID}",
        "application/json",
    )
    result["status_http"] = status_code
    result["status_size_bytes"] = len(status_bytes)
    status_payload: dict[str, Any] = {}
    if status_code == 200:
        status_payload = record(json.loads(status_bytes.decode("utf-8")))
        result["status"] = status_payload.get("status")
        result["commit_sha"] = first_nonempty(
            status_payload.get("commit_sha"),
            record(status_payload.get("repository_snapshot")).get("commit_sha"),
            record(record(status_payload.get("record")).get("identity")).get("commit_sha"),
        )
        result["customer_id"] = first_nonempty(status_payload.get("customer_id"), record(record(status_payload.get("record")).get("identity")).get("customer_id"))
        result["project_id"] = first_nonempty(status_payload.get("project_id"), record(record(status_payload.get("record")).get("identity")).get("project_id"))

    json_code, json_headers, json_bytes = fetch(
        f"/api/nico/assessment/comprehensive-run/{RUN_ID}/report/json",
        "application/json",
    )
    result["report_json_http"] = json_code
    result["report_json_size_bytes"] = len(json_bytes)
    canonical: dict[str, Any] = {}
    if json_code == 200:
        canonical = record(json.loads(json_bytes.decode("utf-8")))
        identity = record(canonical.get("identity"))
        human_evidence = canonical.get("human_evidence") or canonical.get("human_evidence_ledger") or status_payload.get("human_evidence") or record(status_payload.get("record")).get("human_evidence")
        result["canonical_identity"] = {
            "customer_name": first_nonempty(identity.get("customer_name"), identity.get("client_name")),
            "project_name": first_nonempty(identity.get("project_name")),
            "primary_technical_contact": first_nonempty(identity.get("primary_technical_contact"), recursive_first(human_evidence, "primary_technical_contact")),
            "access_method": recursive_first(human_evidence, "access_method"),
            "authorized_scope": recursive_first(human_evidence, "authorized_scope"),
        }
        result["canonical_report_language"] = first_nonempty(canonical.get("report_language"), identity.get("report_language"))

    md_code, md_headers, md_bytes = fetch(
        f"/api/nico/assessment/comprehensive-run/{RUN_ID}/report/markdown",
        "text/markdown",
    )
    result["markdown_http"] = md_code
    result["markdown_size_bytes"] = len(md_bytes)
    markdown = md_bytes.decode("utf-8", errors="replace") if md_code == 200 else ""
    result["markdown_missing_markers"] = {
        "client_display_name_not_supplied": "Client display name: not supplied" in markdown,
        "project_display_name_not_supplied": "Project display name: not supplied" in markdown,
        "primary_technical_contact_not_supplied": "Primary technical contact: not supplied" in markdown,
    }

    pdf_code, pdf_headers, pdf_bytes = fetch(
        f"/api/nico/assessment/comprehensive-run/{RUN_ID}/localized-report/en/pdf",
        "application/pdf",
    )
    result["pdf_http"] = pdf_code
    result["pdf_size_bytes"] = len(pdf_bytes)
    result["pdf_run_id_header"] = pdf_headers.get("x-nico-run-id", "")
    result["pdf_report_language_header"] = pdf_headers.get("x-nico-report-language", "")
    if pdf_code == 200 and pdf_bytes.startswith(b"%PDF"):
        reader = PdfReader(io.BytesIO(pdf_bytes))
        result["pdf_page_count"] = len(reader.pages)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        result["pdf_missing_markers"] = {
            "client_display_name_not_supplied": "Client display name: not supplied" in text,
            "project_display_name_not_supplied": "Project display name: not supplied" in text,
            "primary_technical_contact_not_supplied": "Primary technical contact: not supplied" in text,
        }
        result["pdf_has_customer_not_supplied"] = "Customer\nNot supplied" in text or "Customer Not supplied" in text
        result["pdf_has_project_not_supplied"] = "Project\nNot supplied" in text or "Project Not supplied" in text

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

    # Diagnostic only: nonzero means the run is not fetchable, not that supplied metadata
    # was necessarily absent. Interpretation happens from the emitted artifact.
    return 0 if result.get("pdf_http") == 200 and result.get("report_json_http") == 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
