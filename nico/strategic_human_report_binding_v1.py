from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico.strategic_human_evidence_v1 import (
    VERSION as HUMAN_EVIDENCE_VERSION,
    build_strategic_human_evidence_ledger,
    ledger_json,
    parity_matrix_csv,
    qa_register_csv,
    stakeholder_decision_log_csv,
    strategic_intake_template,
)

VERSION = "nico.strategic_human_report_binding.v1"
_MARKER = "_nico_strategic_human_report_binding_v1"


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _update_canonical_module_status(manifest: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(manifest)
    human_by_id = {str(item.get("module_id") or ""): item for item in _records(ledger.get("modules"))}
    statuses = _records(output.get("module_status"))
    for item in statuses:
        module_id = str(item.get("module_id") or "")
        human = _record(human_by_id.get(module_id))
        if not human:
            continue
        item["status"] = human.get("status") or "not_assessed"
        item["source"] = human.get("source_stage") or "explicit_human_evidence_not_retained"
        item["human_evidence_required"] = True
        item["human_evidence_assurance"] = human.get("assurance") or "NOT ASSESSED"
        item["missing_fields"] = human.get("missing_fields") or []
        item["exclusion_rationale"] = human.get("exclusion_rationale") or ""
    output["module_status"] = statuses
    output["strategic_modules_not_assessed"] = [
        item["module_id"]
        for item in statuses
        if item.get("status") in {"not_assessed", "partial"}
    ]
    output["strategic_modules_excluded_with_rationale"] = [
        item["module_id"]
        for item in statuses
        if item.get("status") == "excluded"
    ]
    output["strategic_human_evidence_status"] = ledger.get("status")
    output["human_evidence_fabrication_allowed"] = False
    unsigned = {key: value for key, value in output.items() if key != "canonical_manifest_sha256"}
    output["canonical_manifest_sha256"] = hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
    return output


def install_strategic_human_report_binding_v1() -> dict[str, Any]:
    current: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "human_evidence_version": HUMAN_EVIDENCE_VERSION,
            "missing_human_evidence_disclosed": True,
            "repository_inference_for_human_facts_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def build_with_human_evidence(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        output = deepcopy(result)
        identity = _record(kwargs.get("identity"))
        stage_results = _record(kwargs.get("stage_results"))
        ledger = build_strategic_human_evidence_ledger(identity=identity, stage_results=stage_results)
        ledger_payload = ledger_json(ledger)
        qa_csv = qa_register_csv(ledger)
        parity_csv = parity_matrix_csv(ledger)
        decisions_csv = stakeholder_decision_log_csv(ledger)
        intake_payload = _canonical_json(strategic_intake_template())

        package = _record(output.get("report_package"))
        package.update(
            {
                "strategic_human_evidence_json": ledger_payload,
                "strategic_human_evidence_sha256": _sha256(ledger_payload),
                "strategic_intake_template_json": intake_payload,
                "strategic_intake_template_sha256": _sha256(intake_payload),
                "functional_qa_register_csv": qa_csv,
                "functional_qa_register_sha256": _sha256(qa_csv),
                "platform_parity_matrix_csv": parity_csv,
                "platform_parity_matrix_sha256": _sha256(parity_csv),
                "stakeholder_decision_log_csv": decisions_csv,
                "stakeholder_decision_log_sha256": _sha256(decisions_csv),
            }
        )

        manifest = _record(output.get("canonical_run_manifest") or package.get("canonical_run_manifest"))
        if manifest:
            manifest = _update_canonical_module_status(manifest, ledger)
            output["canonical_run_manifest"] = manifest
            package["canonical_run_manifest"] = manifest

        evidence_manifest = _record(output.get("evidence_manifest") or package.get("evidence_manifest"))
        exports = _record(evidence_manifest.get("exports"))
        exports.update(
            {
                "strategic_human_evidence_json_sha256": package["strategic_human_evidence_sha256"],
                "strategic_intake_template_json_sha256": package["strategic_intake_template_sha256"],
                "functional_qa_register_csv_sha256": package["functional_qa_register_sha256"],
                "platform_parity_matrix_csv_sha256": package["platform_parity_matrix_sha256"],
                "stakeholder_decision_log_csv_sha256": package["stakeholder_decision_log_sha256"],
            }
        )
        evidence_manifest["exports"] = exports
        evidence_manifest["human_evidence_fabrication_allowed"] = False
        evidence_manifest["strategic_human_evidence_status"] = ledger.get("status")
        package["evidence_manifest"] = evidence_manifest
        package["evidence_manifest_json"] = _canonical_json(evidence_manifest)
        output["evidence_manifest"] = evidence_manifest

        quality = _record(output.get("report_quality_contract") or package.get("report_quality_contract"))
        quality.update(
            {
                "strategic_human_evidence_ledger_present": True,
                "strategic_human_evidence_status": ledger.get("status"),
                "missing_human_evidence_disclosed": bool(ledger.get("incomplete_modules")),
                "explicit_exclusions_require_rationale": True,
                "repository_inference_for_human_facts_allowed": False,
                "functional_qa_register_exported": True,
                "platform_parity_matrix_exported": True,
                "stakeholder_decision_log_exported": True,
            }
        )
        package["report_quality_contract"] = quality
        output["report_quality_contract"] = quality
        output["strategic_human_evidence"] = ledger
        output["strategic_intake_template"] = strategic_intake_template()
        output["report_package"] = package
        return output

    setattr(build_with_human_evidence, _MARKER, True)
    setattr(build_with_human_evidence, "_nico_previous", current)
    report_module.build_comprehensive_report_package = build_with_human_evidence
    return {
        "status": "installed",
        "version": VERSION,
        "human_evidence_version": HUMAN_EVIDENCE_VERSION,
        "human_evidence_ledger_exported": True,
        "qa_register_exported": True,
        "parity_matrix_exported": True,
        "stakeholder_decision_log_exported": True,
        "intake_template_exported": True,
        "missing_human_evidence_disclosed": True,
        "repository_inference_for_human_facts_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_strategic_human_report_binding_v1"]
