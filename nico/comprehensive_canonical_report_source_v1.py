from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_decision_content_restoration_v66 import (
    restore_decision_content,
)
from nico.comprehensive_finding_count_truth_v66 import (
    reconcile_finding_count_truth,
)
from nico.comprehensive_maturity_label_truth_v1 import (
    synchronize_maturity_label_truth,
)
from nico.comprehensive_post_readiness_maturity_truth_v2 import (
    install_post_readiness_maturity_truth,
)
from nico.comprehensive_post_readiness_report_contract_truth_v1 import (
    install_post_readiness_report_contract_truth,
)
from nico.comprehensive_report_content_render_v66 import (
    install_comprehensive_report_content_render_v66,
)
from nico.comprehensive_report_package import (
    VERSION as SOURCE_VERSION,
    _assessment,
    _canonical_hash,
    _decision_summary,
    _now,
    _stage_summary,
    _text,
)
from nico.comprehensive_report_semantic_content_gate_v66 import (
    install_comprehensive_report_semantic_content_gate_v66,
)
from nico.comprehensive_zero_finding_finality_truth_v1 import (
    install_comprehensive_zero_finding_finality_truth_v1,
)

POST_READINESS_MATURITY_TRUTH = install_post_readiness_maturity_truth()
POST_READINESS_REPORT_CONTRACT_TRUTH = (
    install_post_readiness_report_contract_truth()
)
ZERO_FINDING_FINALITY_TRUTH = (
    install_comprehensive_zero_finding_finality_truth_v1()
)

VERSION = "nico.comprehensive_canonical_report_source.v7"
_REQUIRED_IDENTITY_FIELDS = (
    "run_id",
    "repository",
    "commit_sha",
    "evidence_ledger_id",
    "customer_id",
    "project_id",
)
_FINAL_STAGE_ID = "final_comprehensive_report_generation"
_SERVICE_ID = "comprehensive"


def build_canonical_report_source(context: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact canonical report model without rendering legacy artifacts.

    The production v2 publisher is the authoritative Markdown, HTML, JSON, and PDF
    renderer. Building a complete legacy draft first caused the final stage to render,
    rewrite, parse, and hash large artifacts twice. This source reuses the same native
    identity, assessment, stage-summary, and decision-summary functions while omitting
    all pre-v2 artifact rendering.

    Before stage evidence is flattened, one preliminary maturity taxonomy is projected
    into explicit aliases. Installed post-readiness boundaries then apply the final
    client-readiness maturity label and remove only superseded internal report-contract
    diagnostics.

    Retained structured decision findings, exact-SHA production complexity hotspots,
    review-required candidate counts, and separately unscored CI operational context
    are restored into canonical truth before hashing. A zero-finding final register is
    therefore valid only when the retained source package contains neither structured
    decision findings nor actionable exact-SHA production complexity evidence. Any stale
    zero-count aliases in retained stage summaries are synchronized to the restored
    canonical population without modifying scanner or review-candidate counts.

    The compact premium renderer is extended with truthful scanner counts, rich finding
    cards, and separately labeled CI operational health. Duplicate full-page finding
    copies remain removed. A semantic gate blocks publication if any restored finding,
    review-candidate count, or CI operational boundary disappears from client formats.

    The report package and its canonical JSON carry the same explicit Comprehensive
    service identity so every renderer and release verifier reads one unambiguous
    artifact contract.

    A real final-stage invocation always contains retained prior-stage evidence. Empty
    stage mappings are compatibility or synthetic calls and must fall back to the
    delegate instead of being mistaken for a complete production assessment.
    """

    identity = {
        field: _text(context.get(field), 180)
        for field in _REQUIRED_IDENTITY_FIELDS
    }
    missing = [field for field, value in identity.items() if not value]
    if missing:
        return {
            "status": "blocked",
            "reason": "canonical_report_identity_incomplete",
            "missing_identity_fields": missing,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    raw_stages = context.get("prior_stage_results")
    if not isinstance(raw_stages, Mapping) or not raw_stages:
        return {
            "status": "blocked",
            "reason": "canonical_report_stage_results_unavailable",
            **identity,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    stages, maturity_truth = synchronize_maturity_label_truth(raw_stages)
    ordered = [
        _stage_summary(str(stage_id), result)
        for stage_id, result in stages.items()
        if isinstance(result, Mapping) and str(stage_id) != _FINAL_STAGE_ID
    ]
    assessment = _assessment(dict(stages))
    assessment = dict(assessment)
    assessment["repository"] = identity["repository"]
    assessment["commit_sha"] = identity["commit_sha"]
    assessment["run_id"] = identity["run_id"]
    assessment["executive_summary"] = _decision_summary(identity, assessment, ordered)
    assessment["maturity_label_truth"] = deepcopy(maturity_truth)

    canonical = {
        "service_id": _SERVICE_ID,
        "identity": identity,
        "assessment": assessment,
        "stage_summaries": ordered,
        "maturity_label_truth": deepcopy(maturity_truth),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    canonical, assessment, decision_content_restoration = restore_decision_content(
        canonical,
        raw_stages=stages,
        assessment=assessment,
        commit_sha=identity["commit_sha"],
    )
    canonical["assessment"] = assessment
    canonical, finding_count_truth = reconcile_finding_count_truth(canonical)
    assessment = dict(canonical.get("assessment") or {})
    ordered = list(canonical.get("stage_summaries") or [])
    report_content_render = install_comprehensive_report_content_render_v66()
    semantic_content_gate = install_comprehensive_report_semantic_content_gate_v66()

    truth_sha = _canonical_hash(canonical)
    report_id = (
        "comprehensive_report_"
        + _canonical_hash({"identity": identity, "stages": ordered})[:20]
    )
    generated_at = _now()
    package = {
        "service_id": _SERVICE_ID,
        "report_id": report_id,
        "generated_at": generated_at,
        "json": canonical,
        "canonical_truth_sha256": truth_sha,
        "source_artifact_schema": SOURCE_VERSION,
        "canonical_only_source": True,
        "maturity_label_truth": deepcopy(maturity_truth),
        "decision_content_restoration": deepcopy(decision_content_restoration),
        "finding_count_truth": deepcopy(finding_count_truth),
        "report_content_render": deepcopy(report_content_render),
        "semantic_content_gate": deepcopy(semantic_content_gate),
        "post_readiness_maturity_truth_installed": (
            POST_READINESS_MATURITY_TRUTH.get("bound") is True
        ),
        "post_readiness_report_contract_truth_installed": (
            POST_READINESS_REPORT_CONTRACT_TRUTH.get("bound") is True
        ),
        "zero_finding_finality_truth_installed": (
            ZERO_FINDING_FINALITY_TRUTH.get("bound") is True
        ),
        "legacy_markdown_rendered": False,
        "legacy_html_rendered": False,
        "legacy_pdf_rendered": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "status": "complete",
        "reason": "",
        "artifact_schema": VERSION,
        "service_id": _SERVICE_ID,
        "report_id": report_id,
        "generated_at": generated_at,
        "report_package": package,
        "canonical_report": canonical,
        "assessment": assessment,
        "stage_summaries": ordered,
        "maturity_label_truth": deepcopy(maturity_truth),
        "decision_content_restoration": deepcopy(decision_content_restoration),
        "finding_count_truth": deepcopy(finding_count_truth),
        "report_content_render": deepcopy(report_content_render),
        "semantic_content_gate": deepcopy(semantic_content_gate),
        "post_readiness_maturity_truth_installation": deepcopy(
            POST_READINESS_MATURITY_TRUTH
        ),
        "post_readiness_report_contract_truth_installation": deepcopy(
            POST_READINESS_REPORT_CONTRACT_TRUTH
        ),
        "zero_finding_finality_truth_installation": deepcopy(
            ZERO_FINDING_FINALITY_TRUTH
        ),
        "canonical_truth_sha256": truth_sha,
        "canonical_only_source": True,
        "single_artifact_render_required": True,
        **identity,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "POST_READINESS_MATURITY_TRUTH",
    "POST_READINESS_REPORT_CONTRACT_TRUTH",
    "ZERO_FINDING_FINALITY_TRUTH",
    "VERSION",
    "build_canonical_report_source",
]
