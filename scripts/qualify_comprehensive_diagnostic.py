"""Fresh, source-based report diagnostic in an isolated local PostgreSQL service.

This is candidate acceptance evidence, not production qualification or approval.
The actual providers acquire source and run the assessment. An observer retains
the exact final worker context before execution without replacing any provider.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

FINAL_STAGE = "final_comprehensive_report_generation"
MAX_CAPSULE_BYTES = 256 * 1024 * 1024
RENDER_SECONDS = 900.0
IDENTITY_FIELDS = ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def retain(path, raw):
    """Create once inside the private run directory; never overwrite evidence."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != raw:
        raise ValueError("diagnostic_retention_mismatch")
    return {"sha256": digest(raw), "size_bytes": len(raw), "file": path.name}


def isolated_database(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname != "127.0.0.1"
            or parsed.path != "/nico_report_diagnostic"
            or parsed.query or parsed.fragment):
        raise ValueError("dedicated_local_diagnostic_database_required")
    return value


def observe_worker(delegate, output, identities, producer, secrets=()):
    def observed(context, **kwargs):
        run_id = context.get("run_id")
        if run_id not in identities or any(context.get(k) != v for k, v in identities[run_id].items()):
            raise ValueError("diagnostic_context_identity_mismatch")
        if kwargs.get("max_render_seconds") != RENDER_SECONDS:
            raise ValueError("diagnostic_renderer_deadline_changed")
        raw = encoded(context)
        if len(raw) > MAX_CAPSULE_BYTES:
            raise ValueError("diagnostic_context_too_large")
        if any(secret and secret.encode() in raw for secret in secrets):
            raise ValueError("diagnostic_context_contains_runtime_credential")
        locale_directory = output / context["report_language"]
        locale_directory.mkdir(mode=0o700, exist_ok=True)
        directory = locale_directory / ("attempt-" + uuid4().hex)
        directory.mkdir(mode=0o700)
        identity = retain(directory / "renderer-input.json", raw)
        retain(directory / "input-manifest.json", encoded({
            "schema": "nico.fresh-report-diagnostic.input.v1",
            "producer": producer, "identity": identities[run_id],
            "input": identity, "renderer_deadline_seconds": RENDER_SECONDS,
            "historical_replay": False, "production_qualified": False,
        }))
        # The delegate receives the saved JSON values, exactly as its own JSON
        # transport does. No prior result, score, finding or locale is synthesized.
        retained = json.loads((directory / "renderer-input.json").read_bytes())
        if encoded(retained) != raw:
            raise ValueError("diagnostic_context_roundtrip_mismatch")
        try:
            result, execution = delegate(retained, **kwargs)
            result_identity = retain(directory / "renderer-result.json", encoded(result))
            execution_identity = retain(directory / "renderer-execution.json", encoded(execution))
            retain(directory / "outcome-manifest.json", encoded({
                "input": identity, "result": result_identity, "execution": execution_identity,
            }))
            return result, execution
        except BaseException as exc:
            retain(directory / "renderer-error.json", encoded({"error_type": type(exc).__name__}))
            raise
    return observed


def accepted_capture(output, identity, producer, pdf_sha256):
    """Require the successful final PDF to come from a verified retained attempt."""
    matches = []
    for directory in sorted((output / identity["report_language"]).glob("attempt-*")):
        if not (directory / "outcome-manifest.json").is_file():
            continue  # Failed attempts remain retained, never count as acceptance.
        manifest = json.loads((directory / "input-manifest.json").read_bytes())
        outcome = json.loads((directory / "outcome-manifest.json").read_bytes())
        if manifest["identity"] != identity or manifest["producer"] != producer:
            raise ValueError("diagnostic_retained_provenance_mismatch")
        values = {}
        for field, name in (("input", "renderer-input.json"), ("result", "renderer-result.json"),
                            ("execution", "renderer-execution.json")):
            raw = (directory / name).read_bytes()
            if outcome[field] != {"sha256": digest(raw), "size_bytes": len(raw), "file": name}:
                raise ValueError("diagnostic_retained_artifact_mismatch")
            values[field] = json.loads(raw)
        if manifest["input"] != outcome["input"] or any(values["input"].get(k) != v for k, v in identity.items()):
            raise ValueError("diagnostic_retained_input_mismatch")
        package = values["result"].get("report_package") or values["result"].get("reports") or {}
        raw_pdf = base64.b64decode(package.get("pdf_base64") or "", validate=True)
        if raw_pdf and digest(raw_pdf) == pdf_sha256 == package.get("pdf_sha256"):
            if values["execution"].get("render_deadline_seconds") != RENDER_SECONDS:
                raise ValueError("diagnostic_retained_deadline_mismatch")
            matches.append({"attempt": directory.name, "input_sha256": outcome["input"]["sha256"],
                            "result_sha256": outcome["result"]["sha256"]})
    if len(matches) != 1:
        raise ValueError("diagnostic_final_pdf_retained_attempt_not_unique")
    return matches[0]


def final_package(record, identity):
    if record.get("client_delivery_allowed") is not False or record.get("human_review_required") is not True:
        raise ValueError("diagnostic_approval_boundary_changed")
    if record.get("review_history") or record.get("review_decision"):
        raise ValueError("diagnostic_review_action_present")
    if record.get("status") != "review_required" or record.get("terminal") is not True:
        raise ValueError("diagnostic_run_not_review_ready")
    stages = record.get("stage_results") or {}
    stage = stages.get(FINAL_STAGE) or {}
    if FINAL_STAGE not in (record.get("completed_stages") or []) or stage.get("status") != "complete":
        raise ValueError("diagnostic_final_stage_not_complete")
    package = stage.get("report_package") or stage.get("reports")
    if not isinstance(package, dict):
        raise ValueError("diagnostic_final_package_missing")
    canonical = package.get("json") or {}
    actual = canonical.get("identity") or {}
    for key in IDENTITY_FIELDS:
        if actual.get(key) != identity[key]:
            raise ValueError("diagnostic_report_identity_mismatch")
    if package.get("report_language") != identity["report_language"]:
        raise ValueError("diagnostic_report_language_mismatch")
    locales = [mapping[key] for mapping in (canonical, actual) for key in ("report_language", "locale")
               if mapping.get(key)]
    if not locales or any(value != identity["report_language"] for value in locales):
        raise ValueError("diagnostic_canonical_language_mismatch")
    if package.get("human_review_required") is not True or package.get("client_delivery_allowed") is not False:
        raise ValueError("diagnostic_package_approval_boundary_changed")
    raw = base64.b64decode(package.get("pdf_base64") or "", validate=True)
    if not raw.startswith(b"%PDF-") or digest(raw) != package.get("pdf_sha256"):
        raise ValueError("diagnostic_pdf_digest_mismatch")
    return package, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        raise ValueError("diagnostic_repository_invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        raise ValueError("diagnostic_exact_source_required")
    database = isolated_database(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("NICO_DISABLE_POSTGRES", "false").lower() != "false":
        raise ValueError("diagnostic_postgres_required")
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    # The only store is the dedicated local service validated above. No production
    # URL, operator credential, historical record or recovery request is accepted.
    os.environ["NICO_SCANNER_RAW_ARTIFACT_ROOT"] = str(output / "scanner-artifacts")
    producer = {key: subprocess.check_output(["git", "rev-parse", ref], text=True).strip()
                for key, ref in (("source_sha", "HEAD"), ("tree_sha", "HEAD^{tree}"))}
    retain(output / "producer.json", encoded(producer))
    from nico.api.spanish_final_report_bootstrap import app
    from nico import comprehensive_final_report_process_isolation_v1 as isolation
    from nico import comprehensive_final_report_background_v1 as background
    from nico.comprehensive_production_capabilities import build_production_capability_executors
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.comprehensive_runtime import _DetachedProductionComprehensiveRunService
    from nico.storage import STORE
    import psycopg
    if not STORE.persistence_available or background._max_publication_seconds() != RENDER_SECONDS:
        raise ValueError("diagnostic_storage_or_deadline_not_established")
    store = ComprehensiveRunStore(lambda: psycopg.connect(database), dialect="postgres")
    store.ensure_schema()
    service = _DetachedProductionComprehensiveRunService(store, build_production_capability_executors(app))
    identities = {}
    for language in ("en", "es-MX"):
        run_id = "comprun_diagnostic_" + uuid4().hex
        identities[run_id] = {"run_id": run_id, "repository": args.repository,
                              "commit_sha": args.source_sha, "report_language": language,
                              "evidence_ledger_id": "ledger_" + run_id,
                              "customer_id": "diagnostic_owner", "project_id": "diagnostic_nico"}
    retain(output / "runs.json", encoded(identities))
    isolation.run_isolated_final_report = observe_worker(
        isolation.run_isolated_final_report, output, identities, producer,
        [os.environ.get("GITHUB_TOKEN", ""), os.environ.get("NICO_GITHUB_TOKEN", "")])
    results = []
    for run_id, identity in identities.items():
        language = identity["report_language"]
        service.start(**identity, authorized=True, assessment_depth="strategic")
        started = time.monotonic()
        last_progress = None
        record = service.load_read_only(run_id)
        try:
            while not record.get("terminal") and record.get("status") not in {"blocked", "failed", "error"}:
                if time.monotonic() - started > 5400:
                    raise TimeoutError("diagnostic_whole_run_deadline")
                record = service.resume(run_id, max_stages=1)
                progress = (record.get("current_stage"), record.get("status"), len(record.get("completed_stages") or []))
                if progress != last_progress:
                    print(json.dumps({"language": language, "stage": progress[0], "status": progress[1],
                                      "completed_stages": progress[2]}), flush=True)
                    last_progress = progress
                if not record.get("terminal"):
                    time.sleep(2)
            retain(output / (language + "-run.json"), encoded(record))
            package, pdf = final_package(record, identity)
            capture = accepted_capture(output, identity, producer, digest(pdf))
            retain(output / (language + "-report.pdf"), pdf)
            retain(output / (language + "-report.json"), encoded(package))
            results.append({"language": language, "status": "rendered_pending_inspection",
                            "pdf_sha256": digest(pdf), "pdf_bytes": len(pdf), "run_id": run_id,
                            "retained_capture": capture})
        except Exception as exc:
            if not (output / (language + "-run.json")).exists():
                retain(output / (language + "-run.json"), encoded(service.load_read_only(run_id)))
            results.append({"language": language, "status": "failed", "error_type": type(exc).__name__,
                            "error": str(exc)[:240], "run_id": run_id})
    retain(output / "result.json", encoded({"schema": "nico.fresh-report-diagnostic.v1",
        "results": results, "producer": producer, "assessed_source_sha": args.source_sha,
        "historical_replay": False, "production_qualified": False,
        "human_review_required": True, "client_delivery_allowed": False}))
    print(json.dumps(results), flush=True)
    return 0 if all(row["status"] == "rendered_pending_inspection" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
