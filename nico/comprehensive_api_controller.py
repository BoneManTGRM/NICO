from __future__ import annotations

from typing import Any

from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.comprehensive_api_controller.v8"
MAX_PROJECTED_STRING_CHARS = 1_200
MAX_PROJECTED_LIST_ITEMS = 24
MAX_PROJECTED_OBJECT_ITEMS = 24
MAX_PROJECTED_DEPTH = 2

_OMITTED_STAGE_KEYS = {
    "assessment",
    "report_package",
    "reports",
    "pdf_base64",
    "markdown",
    "html",
    "raw_evidence",
    "raw_evidence_json",
    "scanner_outputs",
    "scanner_outputs_json",
    "evidence_artifact_bundle",
    "evidence_bundle_json",
    "evidence_ledger_json",
}
_REPORT_STAGE_IDS = (
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
    "report_generation",
    "reports",
)
_REPORT_MANIFEST_KEYS = (
    "service_id",
    "report_id",
    "report_language",
    "locale",
    "generated_at",
    "generation_timestamp",
    "pdf_filename",
    "pdf_error",
    "pdf_sha256",
    "canonical_truth_sha256",
    "assessment_state",
    "report_finality",
    "approval_status",
    "delivery_status",
    "artifact_delivery",
)


def _ordered_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow canonical-order view without cloning large stage payloads."""

    ordered_record = dict(record)
    raw_results = record.get("stage_results")
    if not isinstance(raw_results, dict):
        ordered_record["stage_results"] = {}
        return ordered_record

    ordered_results: dict[str, Any] = {}
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id in raw_results:
            ordered_results[stage_id] = raw_results[stage_id]
    for stage_id, result in raw_results.items():
        if stage_id not in ordered_results:
            ordered_results[str(stage_id)] = result
    ordered_record["stage_results"] = ordered_results
    return ordered_record


def _bounded_percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, parsed))


def _active_stage_percent(record: dict[str, Any]) -> float | None:
    current_stage = str(record.get("current_stage") or "")
    stage_results = record.get("stage_results")
    if not current_stage or not isinstance(stage_results, dict):
        return None
    result = stage_results.get(current_stage)
    if not isinstance(result, dict):
        return None

    scanner = result.get("scanner")
    if isinstance(scanner, dict):
        nested = _bounded_percent(scanner.get("progress_percent"))
        if nested is not None:
            return nested
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        nested = _bounded_percent(evidence.get("progress_percent"))
        if nested is not None:
            return nested
    return _bounded_percent(result.get("stage_progress_percent"))


def _display_progress(record: dict[str, Any]) -> tuple[float, float | None]:
    """Interpolate active-stage progress for UI display only."""

    canonical = _bounded_percent(record.get("progress_percent")) or 0.0
    if record.get("terminal"):
        return canonical, None
    active = _active_stage_percent(record)
    if active is None:
        return canonical, None
    stage_width = 100.0 / len(COMPREHENSIVE_STAGES)
    interpolated = min(99.99, canonical + (stage_width * active / 100.0))
    return round(max(canonical, interpolated), 2), round(active, 2)


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    """Project JSON-like evidence into a deterministic browser-safe structure."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= MAX_PROJECTED_STRING_CHARS:
            return value
        return value[:MAX_PROJECTED_STRING_CHARS] + "…"
    if depth >= MAX_PROJECTED_DEPTH:
        if isinstance(value, dict):
            return {"type": "object", "item_count": len(value), "bounded": True}
        if isinstance(value, list):
            return {"type": "array", "item_count": len(value), "bounded": True}
        return str(type(value).__name__)
    if isinstance(value, list):
        projected = [
            _bounded_value(item, depth=depth + 1)
            for item in value[:MAX_PROJECTED_LIST_ITEMS]
        ]
        if len(value) > MAX_PROJECTED_LIST_ITEMS:
            projected.append(
                {
                    "bounded": True,
                    "omitted_item_count": len(value) - MAX_PROJECTED_LIST_ITEMS,
                }
            )
        return projected
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_PROJECTED_OBJECT_ITEMS:
                projected["_bounded"] = {
                    "omitted_item_count": len(value) - MAX_PROJECTED_OBJECT_ITEMS,
                }
                break
            projected[str(key)] = _bounded_value(item, depth=depth + 1)
        return projected
    return str(value)[:MAX_PROJECTED_STRING_CHARS]


def _project_stage_result(stage_id: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "stage_id": stage_id,
            "status": "unknown",
            "summary": "Stage result was not an object.",
            "response_bounded": True,
        }

    projected: dict[str, Any] = {
        "stage_id": stage_id,
        "status": str(result.get("status") or "unknown"),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "response_bounded": True,
    }
    for key, value in result.items():
        normalized = str(key)
        if normalized in _OMITTED_STAGE_KEYS or normalized in projected:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            projected[normalized] = _bounded_value(value)
            continue
        if normalized in {
            "evidence",
            "scanner",
            "metrics",
            "coverage",
            "unavailable",
            "findings",
        }:
            projected[normalized] = _bounded_value(value)
    omitted = [key for key in _OMITTED_STAGE_KEYS if key in result]
    if omitted:
        projected["omitted_large_fields"] = sorted(omitted)
    return projected


def _human_evidence_summary(record: dict[str, Any]) -> dict[str, Any]:
    package = record.get("human_evidence")
    if not isinstance(package, dict):
        return {
            "status": "not_assessed",
            "provided_module_ids": [],
            "provided_module_count": 0,
        }
    provided = [str(item) for item in package.get("provided_module_ids") or []]
    return {
        "artifact_schema": str(package.get("artifact_schema") or ""),
        "status": str(package.get("status") or "not_assessed"),
        "provided_module_ids": provided,
        "provided_module_count": len(provided),
        "status_counts": _bounded_value(package.get("status_counts") or {}),
        "human_statement_count": int(package.get("human_statement_count") or 0),
        "attachment_reference_count": int(
            package.get("attachment_reference_count") or 0
        ),
        "structured_record_count": int(package.get("structured_record_count") or 0),
        "human_evidence_sha256": str(package.get("human_evidence_sha256") or ""),
        "repository_inference_prohibited": True,
    }


def _project_record(record: dict[str, Any]) -> dict[str, Any]:
    stage_results = (
        record.get("stage_results")
        if isinstance(record.get("stage_results"), dict)
        else {}
    )
    return {
        "artifact_schema": str(record.get("artifact_schema") or ""),
        "service_id": "comprehensive",
        "status": str(record.get("status") or "unknown"),
        "identity": _bounded_value(
            record.get("identity") if isinstance(record.get("identity"), dict) else {}
        ),
        "engagement_metadata": _bounded_value(
            record.get("engagement_metadata")
            if isinstance(record.get("engagement_metadata"), dict)
            else {}
        ),
        "human_evidence_summary": _human_evidence_summary(record),
        "current_stage": record.get("current_stage"),
        "completed_stages": [str(item) for item in record.get("completed_stages") or []],
        "stage_results": {
            stage_id: _project_stage_result(stage_id, result)
            for stage_id, result in stage_results.items()
        },
        "blockers": _bounded_value(record.get("blockers") or []),
        "progress_percent": record.get("progress_percent"),
        "revision": record.get("revision"),
        "terminal": bool(record.get("terminal")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "integrity_sha256": str(record.get("integrity_sha256") or ""),
        "response_projection": {
            "version": VERSION,
            "bounded": True,
            "persisted_record_mutated": False,
            "large_stage_payloads_omitted": True,
            "report_payload_deferred_to_exact_run_artifact_endpoints": True,
        },
    }


def _report_outputs(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_results = (
        record.get("stage_results")
        if isinstance(record.get("stage_results"), dict)
        else {}
    )
    report: dict[str, Any] = {}
    assessment: dict[str, Any] = {}
    for stage_id in _REPORT_STAGE_IDS:
        stage = stage_results.get(stage_id)
        if not isinstance(stage, dict):
            continue
        if not report:
            candidate = (
                stage.get("report_package")
                if isinstance(stage.get("report_package"), dict)
                else stage.get("reports")
            )
            if isinstance(candidate, dict):
                report = candidate
        if not assessment and isinstance(stage.get("assessment"), dict):
            assessment = stage["assessment"]
        if report and assessment:
            break
    if not report and isinstance(record.get("reports"), dict):
        report = record["reports"]
    if not assessment and isinstance(record.get("assessment"), dict):
        assessment = record["assessment"]
    return report, assessment


def _project_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return only the exact terminal artifact manifest on lifecycle responses.

    Full Markdown, HTML, PDF bytes, and canonical JSON remain immutable in durable run
    truth and are served through their exact-run artifact endpoints. Keeping those large
    artifacts out of status/continuation JSON prevents Safari and other browsers from
    parsing and retaining the entire report package merely to render action controls.
    """

    projected = {
        key: _bounded_value(report[key])
        for key in _REPORT_MANIFEST_KEYS
        if key in report
    }
    projected.update(
        {
            "markdown_available": bool(str(report.get("markdown") or "").strip()),
            "html_available": bool(str(report.get("html") or "").strip()),
            "json_available": isinstance(report.get("json"), dict)
            and bool(report.get("json")),
            "pdf_available": bool(str(report.get("pdf_base64") or "").strip())
            and not bool(str(report.get("pdf_error") or "").strip()),
            "response_bounded": True,
            "artifact_delivery": "on_demand_exact_run",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return projected


def _project_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key in (
        "executive_summary",
        "evidence_coverage",
        "evidence_completion_contract",
        "technical_score",
        "canonical_evidence_adjusted_score",
        "evidence_adjusted_score",
        "maturity_signal",
        "unavailable_data_notes",
        "human_review_required",
        "client_ready",
        "client_delivery_allowed",
    ):
        if key in assessment:
            projected[key] = _bounded_value(assessment[key])

    sections = assessment.get("sections")
    if isinstance(sections, list):
        projected_sections: list[dict[str, Any]] = []
        for section in sections[:MAX_PROJECTED_LIST_ITEMS]:
            if not isinstance(section, dict):
                continue
            item: dict[str, Any] = {}
            for key in (
                "id",
                "label",
                "score",
                "presented_score",
                "status",
                "presented_status",
                "summary",
                "evidence",
                "findings",
                "unavailable",
            ):
                if key in section:
                    item[key] = _bounded_value(section[key])
            projected_sections.append(item)
        projected["sections"] = projected_sections
    projected["human_review_required"] = True
    projected["client_ready"] = False
    projected["client_delivery_allowed"] = False
    return projected


class ComprehensiveApiController:
    """Framework-neutral controller for the customer-facing Comprehensive API.

    The durable store keeps the full canonical run and every report artifact. Lifecycle
    responses expose only a bounded browser-safe projection at every phase, including
    the terminal human-review boundary. Exact report artifacts are retrieved separately
    by run ID, so lifecycle polling never has to carry PDF base64, Markdown, HTML, or
    canonical report JSON. This projection changes transport only; persisted assessment
    truth, report hashes, human review, and delivery authorization remain unchanged.
    """

    def __init__(self, service: ComprehensiveRunService) -> None:
        self._service = service

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._object(payload)
        repository = self._required(body.get("repository"), "repository")
        commit_sha = self._required(body.get("commit_sha"), "commit_sha")
        run_id = self._required(body.get("run_id"), "run_id")
        evidence_ledger_id = self._required(
            body.get("evidence_ledger_id"),
            "evidence_ledger_id",
        )
        customer_id = self._required(body.get("customer_id"), "customer_id")
        project_id = self._required(body.get("project_id"), "project_id")
        assessment_depth = self._required(
            body.get("assessment_depth") or "strategic",
            "assessment_depth",
        )
        report_language = self._required(
            body.get("report_language") or "en",
            "report_language",
        )
        if (
            body.get("authorization_confirmed") is not True
            or body.get("authorized") is not True
        ):
            raise ValueError("explicit_authorization_required")

        engagement_metadata = build_comprehensive_engagement_metadata(
            client_name=body.get("client_name"),
            project_name=body.get("project_name"),
            human_evidence=body.get("human_evidence"),
        )
        record = self._service.start(
            run_id=run_id,
            repository=repository,
            commit_sha=commit_sha,
            evidence_ledger_id=evidence_ledger_id,
            customer_id=customer_id,
            project_id=project_id,
            authorized=True,
            assessment_depth=assessment_depth,
            report_language=report_language,
            human_evidence=body.get("human_evidence"),
            engagement_metadata=engagement_metadata,
        )
        return self._response(record, operation="started")

    def status(self, run_id: str) -> dict[str, Any]:
        record = self._service.load(self._required(run_id, "run_id"))
        return self._response(record, operation="status")

    def continue_run(
        self,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = self._object(payload or {})
        bounded = body.get("max_stages")
        max_stages = None if bounded is None else int(bounded)
        if max_stages is not None and max_stages < 0:
            raise ValueError("max_stages_must_be_non_negative")
        record = self._service.resume(
            self._required(run_id, "run_id"),
            max_stages=max_stages,
        )
        return self._response(record, operation="continued")

    @staticmethod
    def _object(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("request_body_must_be_object")
        return dict(payload)

    @staticmethod
    def _required(value: Any, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field}_required")
        return normalized

    @staticmethod
    def _response(record: dict[str, Any], *, operation: str) -> dict[str, Any]:
        canonical_record = _ordered_record(record)
        identity = canonical_record["identity"]
        display_progress, active_stage_progress = _display_progress(canonical_record)
        terminal = bool(canonical_record.get("terminal"))
        response: dict[str, Any] = {
            "artifact_schema": VERSION,
            "service_id": "comprehensive",
            "operation": operation,
            "run_id": identity["run_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "customer_id": identity["customer_id"],
            "project_id": identity["project_id"],
            "assessment_depth": str(identity.get("assessment_depth") or "strategic"),
            "report_language": str(identity.get("report_language") or "en"),
            "engagement_metadata": _bounded_value(
                canonical_record.get("engagement_metadata")
                if isinstance(canonical_record.get("engagement_metadata"), dict)
                else {}
            ),
            "human_evidence_summary": _human_evidence_summary(canonical_record),
            "status": canonical_record["status"],
            "current_stage": canonical_record["current_stage"],
            "completed_stages": list(canonical_record["completed_stages"]),
            "progress_percent": display_progress,
            "canonical_progress_percent": canonical_record["progress_percent"],
            "active_stage_progress_percent": active_stage_progress,
            "revision": canonical_record["revision"],
            "terminal": terminal,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "integrity_sha256": canonical_record["integrity_sha256"],
            "record": _project_record(canonical_record),
            "response_projection": {
                "version": VERSION,
                "bounded": True,
                "terminal_report_manifest_attached": terminal,
                "terminal_report_artifacts_inlined": False,
                "terminal_canonical_json_attached": False,
                "full_record_persisted": True,
                "large_stage_payloads_omitted": True,
                "exact_run_artifact_endpoints_required": terminal,
            },
        }
        if terminal:
            report, assessment = _report_outputs(canonical_record)
            if report:
                response["reports"] = _project_report(report)
            if assessment:
                response["assessment"] = _project_assessment(assessment)
        return response


__all__ = ["ComprehensiveApiController", "VERSION"]
