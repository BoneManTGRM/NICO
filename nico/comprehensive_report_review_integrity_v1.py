from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "nico.comprehensive_report_review_integrity.v1"
_DISPLAY_METADATA: ContextVar[dict[str, str]] = ContextVar(
    "nico_comprehensive_display_metadata",
    default={},
)
_INSTALLED = False
_STATE: dict[str, Any] = {}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _first(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _text(value[0]) if value else ""
    return _text(value)


def _find_evidence_value(value: Any, key: str) -> str:
    if isinstance(value, Mapping):
        if key in value:
            direct = _first(value.get(key))
            if direct:
                return direct
        for nested in value.values():
            result = _find_evidence_value(nested, key)
            if result:
                return result
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            result = _find_evidence_value(nested, key)
            if result:
                return result
    return ""


def _display_values(record: Mapping[str, Any]) -> dict[str, str]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    human_evidence = record.get("human_evidence") if isinstance(record.get("human_evidence"), Mapping) else {}
    return {
        "customer_name": _text(identity.get("customer_name"), 180),
        "project_name": _text(identity.get("project_name"), 180),
        "primary_technical_contact": _find_evidence_value(
            human_evidence,
            "primary_technical_contact",
        ),
    }


def _install_intake_display_metadata() -> dict[str, bool]:
    import nico.comprehensive_api_routes as routes
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_service import ComprehensiveRunService

    if not getattr(routes._intake, "_nico_display_metadata_v1", False):
        original_intake = routes._intake

        def intake_with_display_metadata(request, payload):
            values = {
                "customer_name": _text(
                    payload.get("client_name") if isinstance(payload, Mapping) else "",
                    180,
                ),
                "project_name": _text(
                    payload.get("project_name") if isinstance(payload, Mapping) else "",
                    180,
                ),
            }
            token = _DISPLAY_METADATA.set(values)
            try:
                return original_intake(request, payload)
            finally:
                _DISPLAY_METADATA.reset(token)

        intake_with_display_metadata._nico_display_metadata_v1 = True
        routes._intake = intake_with_display_metadata

    if not getattr(ComprehensiveApiController.start, "_nico_display_metadata_v1", False):
        original_controller_start = ComprehensiveApiController.start

        def controller_start_with_display_metadata(self, payload):
            inherited = dict(_DISPLAY_METADATA.get() or {})
            if isinstance(payload, Mapping):
                inherited["customer_name"] = _text(
                    payload.get("client_name") or inherited.get("customer_name"),
                    180,
                )
                inherited["project_name"] = _text(
                    payload.get("project_name") or inherited.get("project_name"),
                    180,
                )
            token = _DISPLAY_METADATA.set(inherited)
            try:
                return original_controller_start(self, payload)
            finally:
                _DISPLAY_METADATA.reset(token)

        controller_start_with_display_metadata._nico_display_metadata_v1 = True
        ComprehensiveApiController.start = controller_start_with_display_metadata

    if not getattr(ComprehensiveRunService.start, "_nico_display_metadata_v1", False):
        original_service_start = ComprehensiveRunService.start

        def service_start_with_display_metadata(self, *args, **kwargs):
            record = original_service_start(self, *args, **kwargs)
            values = dict(_DISPLAY_METADATA.get() or {})
            customer_name = _text(values.get("customer_name"), 180)
            project_name = _text(values.get("project_name"), 180)
            if not customer_name and not project_name:
                return record
            updated = deepcopy(record)
            identity = dict(updated.get("identity") or {})
            if customer_name:
                identity["customer_name"] = customer_name
            if project_name:
                identity["project_name"] = project_name
            updated["identity"] = identity
            return self._store.save(
                updated,
                expected_revision=int(record.get("revision") or 0),
            )

        service_start_with_display_metadata._nico_display_metadata_v1 = True
        ComprehensiveRunService.start = service_start_with_display_metadata

    return {
        "intake_display_metadata_bound": True,
        "direct_start_display_metadata_bound": True,
        "display_metadata_persisted_in_canonical_run_identity": True,
    }


def _install_final_report_identity_projection() -> dict[str, bool]:
    import nico.comprehensive_native_providers as native
    from nico.comprehensive_final_report_background_v1 import FinalReportPublicationCoordinator

    if not getattr(FinalReportPublicationCoordinator.advance, "_nico_display_metadata_v1", False):
        original_advance = FinalReportPublicationCoordinator.advance

        def advance_with_display_metadata(self, record, executor, context):
            enriched = dict(context)
            for key, value in _display_values(record).items():
                if value:
                    enriched[key] = value
            return original_advance(self, record, executor, enriched)

        advance_with_display_metadata._nico_display_metadata_v1 = True
        FinalReportPublicationCoordinator.advance = advance_with_display_metadata

    if not getattr(native._identity, "_nico_display_metadata_v1", False):
        original_identity = native._identity

        def identity_with_display_metadata(context):
            output = original_identity(context)
            for key in ("customer_name", "project_name", "primary_technical_contact"):
                value = _text(context.get(key), 300)
                if value:
                    output[key] = value
            return output

        identity_with_display_metadata._nico_display_metadata_v1 = True
        native._identity = identity_with_display_metadata

    return {
        "final_report_context_carries_display_metadata": True,
        "canonical_report_identity_carries_display_metadata": True,
        "primary_technical_contact_projected_from_human_evidence": True,
    }


def _install_required_report_sections() -> dict[str, bool]:
    import nico.v2_premium_report_renderer as renderer

    if getattr(renderer._canonical_stages, "_nico_required_sections_v1", False):
        return {
            "evidence_reconciliation_and_scoring_forced_client_visible": True,
            "client_evidence_summary_surfaces_display_metadata": True,
            "scores_reused_without_recomputation": True,
        }

    original = renderer._canonical_stages

    def canonical_stages_with_required_sections(canonical):
        stages = [deepcopy(dict(item)) for item in original(canonical)]
        spanish = renderer._is_spanish(canonical)
        assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
        technical, adjusted = renderer._score_pair(assessment)
        technical_text = f"{technical}/100" if technical is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
        adjusted_text = f"{adjusted}/100" if adjusted is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")

        reconciliation = renderer._stage(
            "evidence_reconciliation_and_scoring",
            "Conciliación y puntuación de evidencia" if spanish else "Evidence Reconciliation and Scoring",
            (
                "La puntuación canónica se concilia con la evidencia conservada sin recalcular ni inflar las puntuaciones; las limitaciones de evidencia permanecen explícitas."
                if spanish
                else "Canonical scoring is reconciled to retained evidence without recomputing or inflating either score; evidence limitations remain explicit."
            ),
            evidence=[
                (f"Madurez técnica: {technical_text}" if spanish else f"Technical maturity: {technical_text}"),
                (f"Ajuste por evidencia: {adjusted_text}" if spanish else f"Evidence-Adjusted: {adjusted_text}"),
            ],
            unavailable=assessment.get("unavailable_data_notes") or [],
            status="complete",
        )

        client_evidence: list[str] = []
        missing: list[str] = []
        labels = {
            "customer_name": "Nombre mostrado del cliente" if spanish else "Client display name",
            "project_name": "Nombre mostrado del proyecto" if spanish else "Project display name",
            "primary_technical_contact": "Contacto técnico principal" if spanish else "Primary technical contact",
        }
        for key in ("customer_name", "project_name", "primary_technical_contact"):
            value = _text(identity.get(key), 300)
            if value:
                client_evidence.append(f"{labels[key]}: {value}")
            else:
                missing.append(
                    f"{labels[key]}: no proporcionado"
                    if spanish
                    else f"{labels[key]}: not supplied"
                )
        client_summary = renderer._stage(
            "client_evidence_summary",
            "Resumen de evidencia del cliente" if spanish else "Client Evidence Summary",
            (
                "Los metadatos mostrados del cliente y del proyecto son descriptivos y no sustituyen los identificadores canónicos de alcance."
                if spanish
                else "Client and project display metadata are descriptive and do not replace canonical scope identifiers."
            ),
            evidence=client_evidence,
            unavailable=missing,
            status="complete" if client_evidence else "review_required",
        )

        def upsert(stage: dict[str, Any], *, after_tokens: tuple[str, ...] = ()) -> None:
            target_id = _text(stage.get("stage_id"))
            target_title = _text(stage.get("title")).casefold()
            for index, current in enumerate(stages):
                if (
                    _text(current.get("stage_id")) == target_id
                    or _text(current.get("title")).casefold() == target_title
                ):
                    merged = deepcopy(dict(current))
                    merged.update(stage)
                    stages[index] = merged
                    return
            insert_at = len(stages)
            if after_tokens:
                for index, current in enumerate(stages):
                    haystack = (
                        _text(current.get("stage_id")) + " " + _text(current.get("title"))
                    ).casefold()
                    if all(token in haystack for token in after_tokens):
                        insert_at = index + 1
                        break
            stages.insert(insert_at, stage)

        upsert(reconciliation, after_tokens=("repository", "delivery", "evidence"))
        upsert(client_summary)
        return stages

    canonical_stages_with_required_sections._nico_required_sections_v1 = True
    renderer._canonical_stages = canonical_stages_with_required_sections
    return {
        "evidence_reconciliation_and_scoring_forced_client_visible": True,
        "client_evidence_summary_surfaces_display_metadata": True,
        "scores_reused_without_recomputation": True,
    }


def _install_exception_first_delivery_contract() -> dict[str, bool]:
    import nico.comprehensive_client_delivery_contract_v1 as delivery

    if getattr(delivery._candidate_contract, "_nico_exception_first_v1", False):
        return {
            "phase4_exception_first_candidate_contract": True,
            "phase4_final_delivery_requires_phase2_readiness": True,
        }

    def candidate_contract_exception_first(record):
        from nico.comprehensive_review_work_safe_v1 import review_work_projection

        register = delivery._register(record)
        findings = register.get("findings")
        delivery._require(isinstance(findings, list), "malformed_candidate_register")
        try:
            declared = int(register.get("candidate_record_count"))
        except (TypeError, ValueError):
            declared = -1
        delivery._require(declared == len(findings), "candidate_register_count_mismatch")

        ledger = delivery._mapping(record.get("review_work_ledger"))
        dispositions = delivery._mapping(ledger.get("dispositions"))
        candidate_ids: list[str] = []
        triaged = 0
        for row in findings:
            delivery._require(isinstance(row, Mapping), "malformed_candidate_register")
            candidate_id = delivery._text(row.get("candidate_id"))
            delivery._require(bool(candidate_id), "candidate_identity_missing")
            candidate_ids.append(candidate_id)
            lineage = delivery._mapping(row.get("lineage"))
            delivery._require(
                bool(delivery._text(row.get("candidate_lineage_version") or lineage.get("version")))
                and bool(delivery._text(row.get("lineage_status") or lineage.get("status"))),
                "stale_candidate_lineage",
                candidate_id,
            )
            triage = delivery._mapping(row.get("technical_triage"))
            verdict = delivery._text(triage.get("verdict") or row.get("technical_triage_verdict"))
            confidence = triage.get("confidence", row.get("technical_triage_confidence"))
            delivery._require(
                bool(verdict) and confidence not in (None, ""),
                "incomplete_required_technical_triage",
                candidate_id,
            )
            triaged += 1

        delivery._require(
            len(candidate_ids) == len(set(candidate_ids)),
            "duplicate_candidate_identity",
        )
        candidate_set = set(candidate_ids)
        disposition_ids = {delivery._text(value) for value in dispositions if delivery._text(value)}
        unexpected = sorted(disposition_ids - candidate_set)
        delivery._require(
            not unexpected,
            "candidate_disposition_register_mismatch",
            ",".join(unexpected),
        )

        projection = review_work_projection(record)
        required_ids = {
            delivery._text(value)
            for value in projection.get("required_human_disposition_candidate_ids") or []
            if delivery._text(value)
        }
        pending_required = sorted(required_ids - disposition_ids)
        delivery._require(
            not pending_required,
            "human_dispositions_pending",
            ",".join(pending_required),
        )
        delivery._require(
            projection.get("ready_for_final_approval") is True,
            "review_work_not_ready_for_final_approval",
            str(
                {
                    "remaining_candidate_count": projection.get("remaining_candidate_count"),
                    "missing_quality_control_candidate_ids": projection.get("missing_quality_control_candidate_ids"),
                    "open_evidence_request_count": projection.get("open_evidence_request_count"),
                    "unresolved_high_impact_candidate_ids": projection.get("unresolved_high_impact_candidate_ids"),
                }
            ),
        )
        return {
            "total_candidates": len(findings),
            "technical_triage_completed": triaged,
            "required_human_dispositions": len(required_ids),
            "required_human_dispositions_pending": len(pending_required),
            "actual_human_disposition_record_count": len(disposition_ids),
            "exception_first_review": True,
        }

    candidate_contract_exception_first._nico_exception_first_v1 = True
    delivery._candidate_contract = candidate_contract_exception_first
    return {
        "phase4_exception_first_candidate_contract": True,
        "phase4_final_delivery_requires_phase2_readiness": True,
    }


def install_comprehensive_report_review_integrity_v1() -> dict[str, Any]:
    global _INSTALLED, _STATE
    if _INSTALLED:
        return {**_STATE, "status": "already_installed"}

    state = {
        "artifact_schema": VERSION,
        "status": "installed",
        **_install_intake_display_metadata(),
        **_install_final_report_identity_projection(),
        **_install_required_report_sections(),
        **_install_exception_first_delivery_contract(),
        "server_side_approval_readiness_remains_authoritative": True,
        "canonical_scope_ids_unchanged": True,
        "canonical_scores_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    _INSTALLED = True
    _STATE = dict(state)
    return state


__all__ = ["VERSION", "install_comprehensive_report_review_integrity_v1"]
