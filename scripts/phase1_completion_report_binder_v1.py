from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from nico.phase1_completion_report_contract_v1 import (
    SCHEMA,
    dod_rows,
    extract_report,
    load_json,
    pdf_text,
    sha256,
    validate_external,
)
from nico.phase1_completion_report_pdf_v1 import build_appendix, merge_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind successful Phase 1 acceptance evidence into one NICO Comprehensive report.")
    for name in ("source-pdf", "acceptance-json", "audit-json", "release-json", "status-json", "expected-sha", "output-pdf", "output-manifest"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("workflow-run-id", "mobile-run-id", "ios-run-id", "artifact-id", "artifact-name", "artifact-digest", "acceptance-completed-at"):
        parser.add_argument(f"--{name}", default="")
    args = parser.parse_args()

    source = Path(args.source_pdf)
    output = Path(args.output_pdf)
    manifest_path = Path(args.output_manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    text, source_pages = pdf_text(source)
    report = extract_report(text, args.expected_sha)
    acceptance = load_json(Path(args.acceptance_json))
    audit = load_json(Path(args.audit_json))
    release = load_json(Path(args.release_json))
    status = load_json(Path(args.status_json))
    validate_external(acceptance, audit, release, status, args.expected_sha)

    appendix = output.with_suffix(".appendix.tmp.pdf")
    build_appendix(
        appendix,
        report,
        acceptance,
        audit,
        status,
        args.workflow_run_id,
        args.mobile_run_id,
        args.ios_run_id,
        args.artifact_id,
        args.artifact_name,
        args.artifact_digest,
        args.acceptance_completed_at,
    )
    final_pages = merge_pdf(source, appendix, output)
    appendix.unlink(missing_ok=True)

    manifest = {
        "artifact_schema": SCHEMA,
        "status": "passed",
        "report_product": "NICO COMPREHENSIVE",
        "report_variant": "post-acceptance-bound-automated-draft",
        "additional_report_product_created": False,
        "source_report_preserved": True,
        "repository": acceptance.get("authorized_repository") or audit.get("repository"),
        "commit_sha": args.expected_sha,
        "source_report_page_count": source_pages,
        "source_report_sha256": sha256(source),
        "final_report_page_count": final_pages,
        "final_report_sha256": sha256(output),
        "phase1_definition_of_done": [
            {"item": index, "status": "passed", "evidence": evidence}
            for index, (_, _, evidence) in enumerate(dod_rows(report), start=1)
        ],
        "human_review_required": True,
        "human_approval_status": "pending",
        "client_delivery_allowed": False,
        "acceptance": {
            "workflow_run_id": args.workflow_run_id,
            "mobile_run_id": args.mobile_run_id,
            "ios_run_id": args.ios_run_id,
            "passes_required": acceptance.get("passes_required"),
            "passes_completed": acceptance.get("passes_completed"),
            "artifact_id": args.artifact_id,
            "artifact_name": args.artifact_name,
            "artifact_digest": args.artifact_digest,
            "completed_at": args.acceptance_completed_at,
        },
        "structured_audit": {
            "candidate_count": audit.get("candidate_count"),
            "candidate_register_sha256": audit.get("candidate_register_sha256_observed"),
            "cluster_integrity_error_count": audit.get("cluster_integrity_error_count"),
            "score_effect": audit.get("score_effect"),
            "errors": audit.get("errors"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "output_pdf": str(output), "manifest": str(manifest_path), "sha256": manifest["final_report_sha256"], "pages": final_pages}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
