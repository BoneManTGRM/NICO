from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_NICO_ROOT = _ROOT / "nico"


def _load_support_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load four-phase report support module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_nico_package = types.ModuleType("nico")
_nico_package.__path__ = [str(_NICO_ROOT)]
_nico_package.__package__ = "nico"
sys.modules["nico"] = _nico_package

_pdf = _load_support_module(
    "nico.four_phase_completion_report_pdf_v1",
    _NICO_ROOT / "four_phase_completion_report_pdf_v1.py",
)
SCHEMA = _pdf.SCHEMA
build_appendix = _pdf.build_appendix
merge_pdf = _pdf.merge_pdf


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_all_true(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty object")
    failed = sorted(key for key, item in value.items() if item is not True)
    if failed:
        raise ValueError(f"{label} is incomplete: {', '.join(failed)}")


def validate_phase3(phase3: dict[str, Any]) -> None:
    if phase3.get("artifact_schema") != "nico.phase3_completion_observation.v1":
        raise ValueError("Phase 3 completion observation schema is invalid")
    if phase3.get("status") != "satisfied":
        raise ValueError("Phase 3 is not satisfied")
    if phase3.get("product") != "NICO Comprehensive":
        raise ValueError("Phase 3 product identity is not NICO Comprehensive")
    if phase3.get("one_public_product") is not True or phase3.get("one_client_report") is not True:
        raise ValueError("Phase 3 violated the one-product or one-report boundary")
    implementation = phase3.get("implementation") or {}
    if implementation.get("parallel_assessment_pipeline_created") is not False:
        raise ValueError("Phase 3 created a parallel assessment pipeline")
    if implementation.get("canonical_scoring_replaced") is not False:
        raise ValueError("Phase 3 replaced canonical scoring")
    if implementation.get("report_pipeline_replaced") is not False:
        raise ValueError("Phase 3 replaced the Comprehensive report pipeline")
    _require_all_true(phase3.get("negative_paths_proven"), "Phase 3 negative paths")
    _require_all_true(phase3.get("positive_supplied_evidence_paths_proven"), "Phase 3 positive paths")
    boundaries = phase3.get("human_boundaries") or {}
    if boundaries.get("automation_can_create_human_disposition") is not False:
        raise ValueError("Phase 3 permits automated human disposition")
    if boundaries.get("automation_can_create_final_approval") is not False:
        raise ValueError("Phase 3 permits automated final approval")
    if boundaries.get("automation_can_authorize_client_delivery") is not False:
        raise ValueError("Phase 3 permits automated client delivery")


def validate_phase4(phase4: dict[str, Any]) -> None:
    if phase4.get("artifact_schema") != "nico.phase4_controlled_pilot_readiness_observation.v2":
        raise ValueError("Phase 4 completion observation schema is invalid")
    if phase4.get("engineering_status") != "satisfied":
        raise ValueError("Phase 4 Engineering is not satisfied")
    if phase4.get("production_operability_durability_status") != "satisfied":
        raise ValueError("Phase 4 production operability/durability is not satisfied")
    if phase4.get("product") != "NICO Comprehensive" or phase4.get("one_client_report") is not True:
        raise ValueError("Phase 4 violated the one-report product boundary")
    _require_all_true(phase4.get("software_contracts"), "Phase 4 software contracts")
    _require_all_true(phase4.get("durability_recovery_validation"), "Phase 4 durability/recovery validation")
    _require_all_true(phase4.get("security_validation"), "Phase 4 security validation")
    fixtures = phase4.get("repository_agnostic_fixtures")
    if not isinstance(fixtures, list) or len(fixtures) < 3:
        raise ValueError("Phase 4 repository-agnostic fixtures are incomplete")
    if phase4.get("controlled_outside_repository_pilot_status") != "not_executed":
        raise ValueError("Outside-repository pilot status is not truthfully separated")
    boundaries = phase4.get("human_boundaries") or {}
    if boundaries.get("automation_can_create_final_approval") is not False:
        raise ValueError("Phase 4 permits automated final approval")
    if boundaries.get("automation_can_authorize_client_delivery") is not False:
        raise ValueError("Phase 4 permits automated client delivery")
    if boundaries.get("real_human_approval_executed") is not False:
        raise ValueError("Phase 4 fabricated real human approval")


def validate_status(status: dict[str, Any], expected_sha: str) -> None:
    if status.get("artifact_schema") != "nico.phase1-current-head-status.v1":
        raise ValueError("Exact-current-head status snapshot schema is invalid")
    if status.get("commit_sha") != expected_sha:
        raise ValueError("Exact-current-head status snapshot is bound to another SHA")
    required = status.get("required_contexts")
    contexts = status.get("contexts")
    if not isinstance(required, list) or not isinstance(contexts, dict):
        raise ValueError("Exact-current-head status snapshot is malformed")
    expected = {
        "Vercel",
        "NICO Mobile Restart Production Proof",
        "NICO iOS WebKit Paint Proof",
        "NICO Spanish Comprehensive Production Proof",
        "NICO Two-Service Production Acceptance",
        "NICO Production Acceptance Green Watch",
    }
    observed = set(str(item) for item in required)
    if not expected.issubset(observed):
        missing = sorted(expected - observed)
        raise ValueError("Exact-current-head status snapshot omitted required contexts: " + ", ".join(missing))
    for name in required:
        if (contexts.get(name) or {}).get("state") != "success":
            raise ValueError(f"Required exact-current-head context is not successful: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extend the same NICO Comprehensive completion-bound report with Phase 3 and Phase 4 Engineering closure evidence."
    )
    for name in (
        "source-pdf",
        "source-manifest",
        "phase3-json",
        "phase4-json",
        "status-json",
        "expected-sha",
        "output-pdf",
        "output-manifest",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--spanish-run-id", default="")
    parser.add_argument("--green-watch-run-id", default="")
    args = parser.parse_args()

    source = Path(args.source_pdf)
    source_manifest_path = Path(args.source_manifest)
    phase3_path = Path(args.phase3_json)
    phase4_path = Path(args.phase4_json)
    status_path = Path(args.status_json)
    output = Path(args.output_pdf)
    manifest_path = Path(args.output_manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    source_manifest = _load_json(source_manifest_path)
    phase3 = _load_json(phase3_path)
    phase4 = _load_json(phase4_path)
    status = _load_json(status_path)
    if source_manifest.get("status") != "passed":
        raise ValueError("Phase 1/2 completion-bound source manifest did not pass")
    if source_manifest.get("commit_sha") != args.expected_sha:
        raise ValueError("Phase 1/2 completion-bound source manifest is bound to another SHA")
    if source_manifest.get("additional_report_product_created") is not False:
        raise ValueError("Source completion package created an alternate report product")
    validate_phase3(phase3)
    validate_phase4(phase4)
    validate_status(status, args.expected_sha)

    appendix = output.with_suffix(".phase34.appendix.tmp.pdf")
    build_appendix(
        appendix,
        phase3,
        phase4,
        status,
        args.expected_sha,
        spanish_run_id=args.spanish_run_id,
        green_watch_run_id=args.green_watch_run_id,
    )
    final_pages = merge_pdf(source, appendix, output)
    appendix.unlink(missing_ok=True)

    source_pages = int(source_manifest.get("final_report_page_count") or 0)
    if source_pages <= 0 or final_pages <= source_pages:
        raise ValueError("Phase 3/4 completion pages were not appended")

    manifest = {
        **source_manifest,
        "artifact_schema": SCHEMA,
        "status": "passed",
        "report_product": "NICO COMPREHENSIVE",
        "report_variant": "post-acceptance-four-phase-engineering-bound-automated-draft",
        "additional_report_product_created": False,
        "source_report_preserved": True,
        "commit_sha": args.expected_sha,
        "phase12_bound_report_page_count": source_pages,
        "phase12_bound_report_sha256": _sha256(source),
        "final_report_page_count": final_pages,
        "final_report_sha256": _sha256(output),
        "phase3_completion": phase3,
        "phase4_engineering_completion": phase4,
        "production_operability_durability_status": "satisfied",
        "controlled_outside_repository_pilot_status": "not_executed",
        "human_review_required": True,
        "human_approval_status": "pending",
        "client_delivery_allowed": False,
        "exact_current_head": {
            "commit_sha": args.expected_sha,
            "required_contexts": status.get("required_contexts"),
            "contexts": status.get("contexts"),
            "spanish_workflow_run_id": args.spanish_run_id,
            "green_watch_workflow_run_id": args.green_watch_run_id,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "passed",
                "output_pdf": str(output),
                "manifest": str(manifest_path),
                "sha256": manifest["final_report_sha256"],
                "pages": final_pages,
                "phase3_status": phase3["status"],
                "phase4_engineering_status": phase4["engineering_status"],
                "pilot_status": phase4["controlled_outside_repository_pilot_status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
