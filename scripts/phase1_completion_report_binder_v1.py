from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[1]
_NICO_ROOT = _ROOT / "nico"


def _load_support_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Phase 1 report support module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The application package performs runtime installer work in nico/__init__.py.
# This post-acceptance binder needs only deterministic report modules and must
# not initialize the hosted application or inherit its dependency graph.
_nico_package = types.ModuleType("nico")
_nico_package.__path__ = [str(_NICO_ROOT)]
_nico_package.__package__ = "nico"
sys.modules["nico"] = _nico_package

_contract = _load_support_module(
    "nico.phase1_completion_report_contract_v1",
    _NICO_ROOT / "phase1_completion_report_contract_v1.py",
)
_pdf = _load_support_module(
    "nico.phase1_completion_report_pdf_v1",
    _NICO_ROOT / "phase1_completion_report_pdf_v1.py",
)

SCHEMA = _contract.SCHEMA
dod_rows = _contract.dod_rows
extract_report = _contract.extract_report
load_json = _contract.load_json
pdf_text = _contract.pdf_text
sha256 = _contract.sha256
validate_external = _contract.validate_external
build_appendix = _pdf.build_appendix
merge_pdf = _pdf.merge_pdf


PHASE2_IMPLEMENTATION = {
    "software_status": "complete",
    "empirical_specialist_effort_status": "not_yet_measured",
    "empirical_specialist_effort_tracking_issue": 1169,
    "implementation_pull_requests": [
        {
            "pull_request": 1166,
            "branch": "phase2/full-coverage",
            "head_sha": "69669dfbccd87449930f12ceb4d276c9c3dd3d3b",
            "merge_sha": "5ee3f2b1eb2faf46a7b7cc68940be89df683105f",
        },
        {
            "pull_request": 1170,
            "branch": "phase2/closure-truth-single-product-ios-readiness",
            "head_sha": "1a4ce6ec84682ec3f7e32976822592fc8023fc4c",
            "merge_sha": "1520e0f32b36b09fbb3eab2a2232b8a6407229eb",
        },
    ],
    "software_definition_of_done": {
        "exception_queues": True,
        "filter_search_sort_and_expandable_evidence": True,
        "controlled_bulk_human_disposition": True,
        "quality_control_sampling": True,
        "stale_review_invalidation": True,
        "cross_run_project_client_isolation": True,
        "triage_disposition_approval_delivery_separation": True,
        "cross_format_report_truth": True,
        "one_comprehensive_client_report": True,
        "current_head_verification_required": True,
    },
    "automation_can_create_human_disposition": False,
    "automation_can_create_final_approval": False,
    "automation_can_authorize_client_delivery": False,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind successful production acceptance and Phase 2 software-completion evidence into one NICO Comprehensive report.")
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

    acceptance = load_json(Path(args.acceptance_json))
    audit = load_json(Path(args.audit_json))
    release = load_json(Path(args.release_json))
    status = load_json(Path(args.status_json))
    assessed_commit_sha = str(acceptance.get("assessed_commit_sha") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", assessed_commit_sha):
        raise ValueError(
            "Unified Production Acceptance assessed_commit_sha is required"
        )

    text, source_pages = pdf_text(source)
    report = extract_report(text, assessed_commit_sha)
    validate_external(
        acceptance,
        audit,
        release,
        status,
        args.expected_sha,
        assessed_commit_sha,
    )

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

    phase2_completion = {
        **PHASE2_IMPLEMENTATION,
        "source_report_workload": {
            "technical_triage_completed": report["coverage_done"],
            "technical_triage_total": report["coverage_total"],
            "not_actionable": report["not_actionable"],
            "needs_review": report["needs_review"],
            "confirmed": report["confirmed"],
            "individual_attention_count": report["individual"],
            "grouped_review_eligible_count": report["grouped"],
            "grouped_review_cluster_count": report["clusters"],
            "quality_control_pool": report["qc_pool"],
            "human_review_work_units": report["work_units"],
        },
        "human_review_required": True,
        "human_approval_status": "pending",
        "client_delivery_allowed": False,
    }

    manifest = {
        "artifact_schema": SCHEMA,
        "status": "passed",
        "report_product": "NICO COMPREHENSIVE",
        "report_variant": "post-acceptance-bound-automated-draft",
        "additional_report_product_created": False,
        "source_report_preserved": True,
        "repository": acceptance.get("authorized_repository") or audit.get("repository"),
        "commit_sha": args.expected_sha,
        "release_sha": args.expected_sha,
        "assessed_commit_sha": assessed_commit_sha,
        "source_report_commit_sha": assessed_commit_sha,
        "source_report_page_count": source_pages,
        "source_report_sha256": sha256(source),
        "final_report_page_count": final_pages,
        "final_report_sha256": sha256(output),
        "phase1_definition_of_done": [
            {"item": index, "status": "passed", "evidence": evidence}
            for index, (_, _, evidence) in enumerate(dod_rows(report), start=1)
        ],
        "phase2_completion": phase2_completion,
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
            "commit_sha": audit.get("commit_sha"),
            "candidate_count": audit.get("candidate_count"),
            "candidate_register_sha256": audit.get("candidate_register_sha256_observed"),
            "cluster_integrity_error_count": audit.get("cluster_integrity_error_count"),
            "score_effect": audit.get("score_effect"),
            "errors": audit.get("errors"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "output_pdf": str(output), "manifest": str(manifest_path), "sha256": manifest["final_report_sha256"], "pages": final_pages, "phase2_software_status": phase2_completion["software_status"], "phase2_empirical_status": phase2_completion["empirical_specialist_effort_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
