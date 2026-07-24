from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_report_v5 as report_module

VERSION = "nico.canonical_ci_report_binding.v1"
_MARKER = "_nico_canonical_ci_report_binding_v1"


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def install_canonical_ci_report_binding_v1() -> dict[str, Any]:
    current: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "ci_classification_exported": True,
            "ci_classification_hashed": True,
            "raw_ci_logs_exported": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def build_with_ci_classification(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        output = deepcopy(result)
        assessment = _record(output.get("assessment"))
        classification = _record(assessment.get("ci_run_classification"))
        if not classification:
            return output

        payload = _canonical_json(classification)
        package = _record(output.get("report_package"))
        package["ci_run_classification_json"] = payload
        package["ci_run_classification_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        evidence_manifest = _record(output.get("evidence_manifest") or package.get("evidence_manifest"))
        exports = _record(evidence_manifest.get("exports"))
        exports["ci_run_classification_json_sha256"] = package["ci_run_classification_sha256"]
        evidence_manifest["exports"] = exports
        package["evidence_manifest"] = evidence_manifest
        package["evidence_manifest_json"] = _canonical_json(evidence_manifest)

        artifact_manifest = [
            deepcopy(item)
            for item in (output.get("premium_artifact_manifest") or package.get("premium_artifact_manifest") or [])
            if isinstance(item, dict)
        ]
        for item in artifact_manifest:
            if item.get("artifact_id") == "ci_run_classification_json":
                item["status"] = "ready"
        package["premium_artifact_manifest"] = artifact_manifest

        quality = _record(output.get("report_quality_contract") or package.get("report_quality_contract"))
        quality["ci_run_classification_exported"] = True
        quality["ci_run_classification_hashed"] = True
        quality["unclassified_ci_runs_disclosed"] = "unclassified_non_success_runs" in classification
        package["report_quality_contract"] = quality

        output["ci_run_classification"] = classification
        output["evidence_manifest"] = evidence_manifest
        output["premium_artifact_manifest"] = artifact_manifest
        output["report_quality_contract"] = quality
        output["report_package"] = package
        return output

    setattr(build_with_ci_classification, _MARKER, True)
    setattr(build_with_ci_classification, "_nico_previous", current)
    report_module.build_comprehensive_report_package = build_with_ci_classification
    return {
        "status": "installed",
        "version": VERSION,
        "ci_classification_exported": True,
        "ci_classification_hashed": True,
        "expected_cancellations_identified": True,
        "unclassified_ci_runs_disclosed": True,
        "raw_ci_logs_exported": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_canonical_ci_report_binding_v1"]
