from __future__ import annotations

from typing import Any

from nico.decision_grade_readiness_v1 import DecisionGradeAssessment, validate_report_readiness
from nico.decision_grade_types_v1 import AssessmentIdentity, AssessmentType, VERSION


def text(value: Any, default: str = "") -> str:
    normalized = " ".join(str(value or "").split())
    return normalized or default


def normalize_assessment_type(value: Any) -> AssessmentType:
    normalized = text(value).casefold().replace("-", "_")
    if normalized in {"express", "core", "fast"}:
        return AssessmentType.EXPRESS
    if normalized in {"mid", "middle"}:
        return AssessmentType.MID
    return AssessmentType.COMPREHENSIVE


def build_decision_grade_contract(payload: dict[str, Any], *, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = dict(identity or {})
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else payload.get("report_package") if isinstance(payload.get("report_package"), dict) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = assessment.get("technical_score")
    if not isinstance(technical, (int, float)):
        technical = maturity.get("technical_score") if isinstance(maturity.get("technical_score"), (int, float)) else maturity.get("score")
    adjusted = assessment.get("canonical_evidence_adjusted_score")
    if not isinstance(adjusted, (int, float)):
        adjusted = assessment.get("evidence_adjusted_score")

    package = DecisionGradeAssessment(
        identity=AssessmentIdentity(
            assessment_id=text(identity.get("run_id") or payload.get("run_id") or payload.get("assessment_run_id"), "unknown_run"),
            assessment_type=normalize_assessment_type(identity.get("assessment_depth") or payload.get("assessment_type") or payload.get("assessment_depth")),
            repository=text(identity.get("repository") or payload.get("repository"), "unknown_repository"),
            repository_url=text(payload.get("repository_url")) or None,
            branch=text(payload.get("branch")) or None,
            commit_sha=text(identity.get("commit_sha") or payload.get("commit_sha"), "0000000"),
            commit_timestamp=text(payload.get("commit_timestamp")) or None,
            started_at=text(payload.get("started_at") or payload.get("assessment_started_at")) or None,
            completed_at=text(payload.get("completed_at") or payload.get("assessment_completed_at")) or None,
            duration_seconds=payload.get("duration_seconds") if isinstance(payload.get("duration_seconds"), (int, float)) else None,
            nico_version=text(payload.get("nico_version"), "unknown"),
            scanner_configuration_version=text(payload.get("scanner_configuration_version"), "unknown"),
            report_template_version=text(reports.get("report_template_version"), "unknown"),
            previous_assessment_id=text(payload.get("previous_assessment_id")) or None,
        ),
        technical_score=float(technical) if isinstance(technical, (int, float)) else None,
        evidence_adjusted_score=float(adjusted) if isinstance(adjusted, (int, float)) else None,
        scope_boundaries=[text(item) for item in payload.get("scope_boundaries", []) if text(item)] if isinstance(payload.get("scope_boundaries"), list) else [],
        report_artifact_digest=text(identity.get("report_sha256") or reports.get("pdf_sha256")) or None,
    )
    readiness = validate_report_readiness(package)
    return {"schema_version": VERSION, "assessment": package.model_dump(mode="json"), "readiness": readiness.model_dump(mode="json")}
