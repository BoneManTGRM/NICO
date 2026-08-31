from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_decision_content_restoration_v67 import (
    restore_decision_content,
)
from nico.comprehensive_engagement_metadata_v1 import (
    _literal,
    display_identity_projection,
    normalize_comprehensive_engagement_metadata,
    verify_comprehensive_engagement_metadata,
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
from nico.comprehensive_spanish_publication_preflight_v93 import (
    assert_spanish_canonical_publication_preflight,
    install_spanish_publication_preflight_v93,
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


def _report_language(context: Mapping[str, Any]) -> str:
    identity = context.get("identity") if isinstance(context.get("identity"), Mapping) else {}
    for candidate in (
        identity.get("report_language"),
        context.get("report_language"),
        context.get("locale"),
    ):
        normalized = _text(candidate, 32).casefold().replace("_", "-")
        if normalized.startswith("es"):
            return "es-MX"
        if normalized.startswith("en"):
            return "en"
    return "en"


def _attach_engagement_identity(
    identity: dict[str, Any],
    context: Mapping[str, Any],
) -> None:
    """Project only verified client-supplied metadata into canonical identity.

    The durable engagement snapshot is the sole source for these display/context
    fields. Missing values remain absent and are never reconstructed from repository,
    customer/project scope IDs, or any later analysis stage. A snapshot whose stored
    digest does not verify is treated as unavailable rather than silently normalized.
    """

    raw_metadata = context.get("engagement_metadata")
    if not verify_comprehensive_engagement_metadata(raw_metadata):
        return
    engagement_metadata = normalize_comprehensive_engagement_metadata(raw_metadata)
    if not engagement_metadata:
        return

    projected = display_identity_projection(engagement_metadata)
    optional_identity = {
        "customer_name": projected.get("customer_name"),
        "project_name": projected.get("project_name"),
        "primary_technical_contact": projected.get("primary_technical_contact"),
        "access_method": engagement_metadata.get("access_method"),
        "authorized_scope": engagement_metadata.get("authorized_scope"),
    }
    limits = {
        "customer_name": 180,
        "project_name": 180,
        "primary_technical_contact": 600,
        "access_method": 1200,
        "authorized_scope": 4000,
    }
    for field, value in optional_identity.items():
        literal = _literal(value, limits[field])
        if literal:
            identity[field] = literal

    metadata_sha = _text(
        engagement_metadata.get("engagement_metadata_sha256"),
        128,
    )
    if metadata_sha:
        identity["engagement_metadata_sha256"] = metadata_sha


def build_canonical_report_source(context: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact canonical report model without rendering legacy artifacts.

    Retained decision findings and exact-SHA production complexity hotspots are restored
    into canonical truth before hashing. For Spanish runs, the fully restored model is
    then preflighted through the same strict presentation translator before any client
    artifact renders. This ordering is required because generated finding prose can be
    created during restoration and therefore does not exist in raw prior-stage input.
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

    _attach_engagement_identity(identity, context)

    report_language = _report_language(context)
    identity["report_language"] = report_language
    generated_at = _text(context.get("generated_at"), 80) or _now()
    identity["generated_at"] = generated_at
    identity["generation_timestamp"] = generated_at

    raw_stages = context.get("prior_stage_results")
    if not isinstance(raw_stages, Mapping) or not raw_stages:
        return {
            "status": "blocked",
            "reason": "canonical_report_stage_results_unavailable",
            **identity,
            "report_language": report_language,
            "locale": report_language,
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
    assessment["report_language"] = report_language
    assessment["locale"] = report_language
    assessment["executive_summary"] = _decision_summary(identity, assessment, ordered)
    assessment["maturity_label_truth"] = deepcopy(maturity_truth)

    canonical = {
        "service_id": _SERVICE_ID,
        "identity": identity,
        "report_language": report_language,
        "locale": report_language,
        "generated_at": generated_at,
        "generation_timestamp": generated_at,
        "assessment": assessment,
        "stage_summaries": ordered,
        "maturity_label_truth": deepcopy(maturity_truth),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    raw_engagement_metadata = context.get("engagement_metadata")
    if verify_comprehensive_engagement_metadata(raw_engagement_metadata):
        canonical["engagement_metadata"] = (
            normalize_comprehensive_engagement_metadata(raw_engagement_metadata)
        )
    canonical, assessment, decision_content_restoration = restore_decision_content(
        canonical,
        raw_stages=stages,
        assessment=assessment,
        commit_sha=identity["commit_sha"],
    )
    canonical["assessment"] = assessment
    canonical, finding_count_truth = reconcile_finding_count_truth(canonical)

    # Installation is explicit at the post-restoration canonical boundary so tests can
    # inspect the scanner independently and later v88 rebinds keep the fallback helper.
    spanish_preflight_installation = install_spanish_publication_preflight_v93()
    spanish_preflight = assert_spanish_canonical_publication_preflight(canonical)

    assessment = dict(canonical.get("assessment") or {})
    ordered = list(canonical.get("stage_summaries") or [])
    report_content_render = install_comprehensive_report_content_render_v66()
    semantic_content_gate = install_comprehensive_report_semantic_content_gate_v66()

    truth_sha = _canonical_hash(canonical)
    report_id = (
        "comprehensive_report_"
        + _canonical_hash({"identity": identity, "stages": ordered})[:20]
    )
    package = {
        "service_id": _SERVICE_ID,
        "report_id": report_id,
        "report_language": report_language,
        "locale": report_language,
        "generated_at": generated_at,
        "generation_timestamp": generated_at,
        "json": canonical,
        "canonical_truth_sha256": truth_sha,
        "source_artifact_schema": SOURCE_VERSION,
        "canonical_only_source": True,
        "maturity_label_truth": deepcopy(maturity_truth),
        "decision_content_restoration": deepcopy(decision_content_restoration),
        "finding_count_truth": deepcopy(finding_count_truth),
        "spanish_publication_preflight_installation": deepcopy(
            spanish_preflight_installation
        ),
        "spanish_publication_preflight": deepcopy(spanish_preflight),
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
        "report_language": report_language,
        "locale": report_language,
        "generated_at": generated_at,
        "generation_timestamp": generated_at,
        "report_package": package,
        "canonical_report": canonical,
        "assessment": assessment,
        "stage_summaries": ordered,
        "maturity_label_truth": deepcopy(maturity_truth),
        "decision_content_restoration": deepcopy(decision_content_restoration),
        "finding_count_truth": deepcopy(finding_count_truth),
        "spanish_publication_preflight_installation": deepcopy(
            spanish_preflight_installation
        ),
        "spanish_publication_preflight": deepcopy(spanish_preflight),
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
