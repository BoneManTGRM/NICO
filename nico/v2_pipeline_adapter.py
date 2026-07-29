from __future__ import annotations

import base64
from copy import deepcopy
from typing import Any, Mapping

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.v2_assessment_pipeline import (
    AssessmentState,
    build_canonical_assessment,
    canonical_truth_sha256,
    derive_assessment_state,
)


def apply_v2_pipeline(result: Mapping[str, Any]) -> dict[str, Any]:
    finalized = deepcopy(dict(result))
    package = deepcopy(dict(finalized.get("report_package") or {}))
    raw_canonical = package.get("json") or finalized.get("canonical_report")
    if not isinstance(raw_canonical, Mapping):
        raise ValueError("v2 pipeline requires canonical report JSON")

    canonical = build_canonical_assessment(raw_canonical)
    digest = canonical_truth_sha256(canonical)
    package["json"] = canonical
    package["canonical_findings"] = deepcopy(canonical["canonical_findings"])
    package["findings_register"] = deepcopy(canonical["findings_register"])
    package["canonical_truth_sha256"] = digest
    package = rebuild_client_artifacts(package)
    package["canonical_truth_sha256"] = digest
    package["markdown_canonical_sha256"] = digest
    package["pdf_canonical_sha256"] = digest
    package["ui_canonical_sha256"] = digest

    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("v2 pipeline generated invalid PDF")

    state = derive_assessment_state(
        package_complete=True,
        review_required=True,
        review_approved=False,
        client_delivery_allowed=False,
    )
    if state is not AssessmentState.REVIEW_REQUIRED:
        raise ValueError("complete unapproved package must be review_required")

    finalized["report_package"] = package
    finalized["canonical_report"] = canonical
    finalized["assessment_state"] = state.value
    finalized["status"] = state.value
    finalized["human_review_required"] = True
    finalized["human_review_completed"] = False
    finalized["client_delivery_allowed"] = False
    record = deepcopy(dict(finalized.get("record") or {}))
    record.update(
        {
            "assessment_state": state.value,
            "status": state.value,
            "assessment_package_complete": True,
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "canonical_truth_sha256": digest,
        }
    )
    finalized["record"] = record
    return finalized


__all__ = ["apply_v2_pipeline"]
