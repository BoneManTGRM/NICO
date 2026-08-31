from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "nico.comprehensive_report_review_integrity.v1.1"
_DISPLAY_METADATA: ContextVar[dict[str, str]] = ContextVar(
    "nico_comprehensive_display_metadata",
    default={},
)
_INSTALLED = False
_STATE: dict[str, Any] = {}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _display_literal(value: Any, limit: int) -> str:
    from nico.comprehensive_engagement_metadata_v1 import _literal

    return _literal(value, limit)


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
    engagement = (
        record.get("engagement_metadata")
        if isinstance(record.get("engagement_metadata"), Mapping)
        else {}
    )
    human_evidence = record.get("human_evidence") if isinstance(record.get("human_evidence"), Mapping) else {}
    from nico.comprehensive_engagement_metadata_v1 import (
        normalize_comprehensive_engagement_metadata,
        verify_comprehensive_engagement_metadata,
    )

    if verify_comprehensive_engagement_metadata(engagement):
        verified = normalize_comprehensive_engagement_metadata(engagement)
        return {
            "customer_name": _display_literal(verified.get("client_name"), 180),
            "project_name": _display_literal(verified.get("project_name"), 180),
            "primary_technical_contact": _display_literal(
                verified.get("primary_technical_contact"), 600
            ),
            "access_method": _display_literal(verified.get("access_method"), 1200),
            "authorized_scope": _display_literal(verified.get("authorized_scope"), 4000),
        }

    # Legacy records without a durable verified engagement snapshot may use their
    # historical identity/evidence fallback. Never mix this fallback into a verified
    # snapshot because an explicitly empty field must remain independently empty.
    return {
        "customer_name": _display_literal(identity.get("customer_name"), 180),
        "project_name": _display_literal(identity.get("project_name"), 180),
        "primary_technical_contact": _display_literal(
            identity.get("primary_technical_contact")
            or _find_evidence_value(human_evidence, "primary_technical_contact"),
            600,
        ),
        "access_method": _display_literal(
            identity.get("access_method")
            or _find_evidence_value(human_evidence, "access_method"),
            1200,
        ),
        "authorized_scope": _display_literal(
            identity.get("authorized_scope")
            or _find_evidence_value(human_evidence, "authorized_scope"),
            4000,
        ),
    }


def _display_state_values(
    record: Mapping[str, Any],
    *,
    spanish: bool,
) -> dict[str, str]:
    """Render all five fields from one verified canonical state snapshot."""

    engagement = (
        record.get("engagement_metadata")
        if isinstance(record.get("engagement_metadata"), Mapping)
        else {}
    )
    from nico.comprehensive_engagement_metadata_v1 import (
        render_engagement_field,
        verify_comprehensive_engagement_metadata,
    )

    if verify_comprehensive_engagement_metadata(engagement):
        locale = "es-MX" if spanish else "en"
        return {
            "customer_name": render_engagement_field(
                engagement, "client_name", locale
            ),
            "project_name": render_engagement_field(
                engagement, "project_name", locale
            ),
            "primary_technical_contact": render_engagement_field(
                engagement, "primary_technical_contact", locale
            ),
            "access_method": render_engagement_field(
                engagement, "access_method", locale
            ),
            "authorized_scope": render_engagement_field(
                engagement, "authorized_scope", locale
            ),
        }

    fallback = _display_values(record)
    missing = "No proporcionado" if spanish else "Not supplied"
    return {key: value or missing for key, value in fallback.items()}


_CLIENT_SUMMARY_CANONICAL_PREFIXES = (
    "Client name:",
    "Project name:",
    "Primary technical contact:",
    "Access method:",
    "Authorized scope:",
    "Nombre del cliente:",
    "Nombre del proyecto:",
    "Contacto técnico principal:",
    "Método de acceso:",
    "Alcance autorizado:",
    "Repository identity:",
    "Exact commit:",
    "Run ID:",
    "Technical maturity:",
    "Evidence-adjusted maturity:",
    "Client Evidence Completeness:",
    "Runtime Acceptance:",
    "Scanner execution:",
    "Technical-triage status:",
    "Candidate state:",
    "Human-review workload:",
    "Review state:",
    "Approval state:",
    "Client-delivery state:",
    "Identidad del repositorio:",
    "Commit exacto:",
    "ID de ejecución:",
    "Madurez técnica:",
    "Madurez ajustada por evidencia:",
    "Integridad de la evidencia del cliente:",
    "Aceptación en ejecución:",
    "Ejecución de analizadores:",
    "Estado del triaje técnico:",
    "Estado de candidatos:",
    "Carga de revisión humana:",
    "Estado de revisión:",
    "Estado de aprobación:",
    "Estado de entrega al cliente:",
)


def _retained_client_summary_lines(values: Any) -> list[str]:
    output: list[str] = []
    for value in values or []:
        line = str(value)
        if line.lstrip().startswith(_CLIENT_SUMMARY_CANONICAL_PREFIXES):
            continue
        if line not in output:
            output.append(line)
    return output


def _engagement_completeness(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    engagement = (
        canonical.get("engagement_metadata")
        if isinstance(canonical.get("engagement_metadata"), Mapping)
        else {}
    )
    from nico.comprehensive_engagement_metadata_v1 import (
        engagement_field_states,
        verify_comprehensive_engagement_metadata,
    )

    if not verify_comprehensive_engagement_metadata(engagement):
        return "Limitada" if spanish else "Limited"
    states = engagement_field_states(engagement)
    supplied_or_disposed = sum(
        str(record.get("state") or "") != "not_supplied"
        for record in states.values()
    )
    if supplied_or_disposed == len(states):
        return "Completa" if spanish else "Complete"
    if supplied_or_disposed:
        return "Parcial" if spanish else "Partial"
    return "Limitada" if spanish else "Limited"


def _runtime_acceptance(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    acceptance = canonical.get("production_acceptance")
    if isinstance(acceptance, Mapping):
        status = str(
            acceptance.get("status")
            or acceptance.get("runtime_acceptance_status")
            or ""
        ).strip().casefold().replace("-", "_")
        if status in {"proven", "verified", "complete", "established"}:
            return "Demostrada" if spanish else "Proven"
        if status in {"excluded", "excluded_from_scope", "not_applicable"}:
            return "Excluida" if spanish else "Excluded"

    stage_sources = (
        canonical.get("stage_summaries"),
        (canonical.get("assessment") or {}).get("stage_summaries")
        if isinstance(canonical.get("assessment"), Mapping)
        else None,
    )
    observed = False
    excluded = False
    for source in stage_sources:
        if not isinstance(source, Sequence) or isinstance(
            source,
            (str, bytes, bytearray),
        ):
            continue
        for raw in source:
            if not isinstance(raw, Mapping):
                continue
            stage_id = str(raw.get("stage_id") or "").casefold()
            if not stage_id.startswith("client_human_evidence_") or not any(
                token in stage_id for token in ("functional_qa", "platform_parity")
            ):
                continue
            status = str(raw.get("status") or "").casefold()
            is_excluded = "excluded" in status
            excluded = excluded or is_excluded
            observed = observed or (not is_excluded and bool(raw.get("evidence")))
    if observed:
        return "Parcial" if spanish else "Partial"
    if excluded:
        return "Excluida" if spanish else "Excluded"
    return "No establecida" if spanish else "Not established"


def _client_summary_truth_evidence(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
    technical_text: str,
    adjusted_text: str,
) -> list[str]:
    """Render useful summary facts directly from the same canonical assessment."""

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    lifecycle = canonical.get("lifecycle") if isinstance(canonical.get("lifecycle"), Mapping) else {}
    scanner_summary = assessment.get("scanner_execution_summary") if isinstance(assessment.get("scanner_execution_summary"), Mapping) else {}
    scanner_records = canonical.get("scanner_execution_records")
    if not isinstance(scanner_records, list):
        scanner_records = assessment.get("scanner_execution_records") or []
    scanner_records = [item for item in scanner_records if isinstance(item, Mapping)]

    def number(source: Mapping[str, Any], *keys: str, default: int = 0) -> int:
        for key in keys:
            if source.get(key) is not None:
                try:
                    return int(source.get(key))
                except (TypeError, ValueError):
                    continue
        return default

    requested = number(scanner_summary, "record_count", "requested_count", default=len(scanner_records))
    completed = number(
        scanner_summary,
        "completed_count",
        default=sum(item.get("completed") is True for item in scanner_records),
    )
    incomplete = number(
        scanner_summary,
        "incomplete_count",
        default=max(0, requested - completed),
    )

    candidates = canonical.get("review_candidate_summary")
    if not isinstance(candidates, Mapping):
        candidates = assessment.get("review_candidate_summary") or {}
    if not isinstance(candidates, Mapping):
        candidates = {}
    raw_candidates = number(candidates, "raw_total", "total_raw")
    review_required = number(candidates, "review_required_total", "review_required")
    confirmed = number(candidates, "verified_material_total", "confirmed_material")

    triage: Mapping[str, Any] = {}
    for stage in [
        *(canonical.get("stage_summaries") or []),
        *(assessment.get("stage_summaries") or []),
    ]:
        if isinstance(stage, Mapping) and isinstance(stage.get("technical_triage"), Mapping):
            triage = stage["technical_triage"]
            break
    if isinstance(canonical.get("technical_triage"), Mapping):
        triage = canonical["technical_triage"]
    if isinstance(assessment.get("technical_triage"), Mapping):
        triage = assessment["technical_triage"]
    workload = triage.get("workload_metrics") if isinstance(triage.get("workload_metrics"), Mapping) else {}
    triage_status = str(triage.get("status") or "not_supplied")
    triage_completed = number(workload, "technical_triage_completed")
    triage_pending = number(workload, "technical_triage_pending", default=review_required)
    work_units = number(triage, "human_review_work_units", default=number(workload, "human_review_work_units", default=review_required))

    def state(value: Any) -> str:
        raw = str(value or "not_supplied")
        if not spanish:
            return raw
        return {
            "approved": "aprobada",
            "approved_final": "aprobación final",
            "authorized": "autorizada",
            "blocked": "bloqueada",
            "blocked_pending_human_approval": "bloqueada hasta la aprobación humana",
            "complete": "completado",
            "pending": "pendiente",
            "pending_human_approval": "aprobación humana pendiente",
            "not_supplied": "no suministrado",
        }.get(raw.casefold(), raw)

    review_state = state(
        lifecycle.get("human_review_status")
        or assessment.get("human_review_status")
        or canonical.get("human_review_status")
    )
    approval_state = state(canonical.get("approval_status") or canonical.get("approval_state"))
    delivery_state = state(
        lifecycle.get("client_delivery_status")
        or assessment.get("client_delivery_status")
        or canonical.get("delivery_status")
    )
    if spanish:
        return [
            f"Identidad del repositorio: {identity.get('repository') or 'no suministrado'}",
            f"Commit exacto: {identity.get('commit_sha') or 'no suministrado'}",
            f"ID de ejecución: {identity.get('run_id') or 'no suministrado'}",
            f"Madurez técnica: {technical_text}",
            f"Madurez ajustada por evidencia: {adjusted_text}",
            f"Integridad de la evidencia del cliente: {_engagement_completeness(canonical, spanish=True)}",
            f"Aceptación en ejecución: {_runtime_acceptance(canonical, spanish=True)}",
            f"Ejecución de analizadores: solicitados={requested}; completados={completed}; incompletos={incomplete}",
            f"Estado del triaje técnico: {state(triage_status)}; completados={triage_completed}; pendientes={triage_pending}",
            f"Estado de candidatos: brutos={raw_candidates}; requieren revisión={review_required}; materiales confirmados={confirmed}",
            f"Carga de revisión humana: unidades de trabajo={work_units}; candidatos que requieren revisión={review_required}",
            f"Estado de revisión: {review_state}",
            f"Estado de aprobación: {approval_state}",
            f"Estado de entrega al cliente: {delivery_state}",
        ]
    return [
        f"Repository identity: {identity.get('repository') or 'not supplied'}",
        f"Exact commit: {identity.get('commit_sha') or 'not supplied'}",
        f"Run ID: {identity.get('run_id') or 'not supplied'}",
        f"Technical maturity: {technical_text}",
        f"Evidence-adjusted maturity: {adjusted_text}",
        f"Client Evidence Completeness: {_engagement_completeness(canonical, spanish=False)}",
        f"Runtime Acceptance: {_runtime_acceptance(canonical, spanish=False)}",
        f"Scanner execution: requested={requested}; completed={completed}; incomplete={incomplete}",
        f"Technical-triage status: {triage_status}; completed={triage_completed}; pending={triage_pending}",
        f"Candidate state: raw={raw_candidates}; review required={review_required}; confirmed material={confirmed}",
        f"Human-review workload: work units={work_units}; candidates requiring review={review_required}",
        f"Review state: {review_state}",
        f"Approval state: {approval_state}",
        f"Client-delivery state: {delivery_state}",
    ]


def _install_intake_display_metadata() -> dict[str, bool]:
    import nico.comprehensive_api_routes as routes
    import nico.comprehensive_run_service as run_service_module
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_record import _record_hash

    if not getattr(routes._intake, "_nico_display_metadata_v1", False):
        original_intake = routes._intake

        def intake_with_display_metadata(request, payload):
            values = {
                "customer_name": _display_literal(
                    payload.get("client_name") if isinstance(payload, Mapping) else "",
                    180,
                ),
                "project_name": _display_literal(
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
                inherited["customer_name"] = _display_literal(
                    payload.get("client_name") or inherited.get("customer_name"),
                    180,
                )
                inherited["project_name"] = _display_literal(
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

    # Persist optional display metadata in the initial canonical record before the
    # durable store creates it. This preserves the store's one-revision-per-save
    # contract and keeps the record integrity hash valid.
    if not getattr(run_service_module.create_comprehensive_run_record, "_nico_display_metadata_v1", False):
        original_create_record = run_service_module.create_comprehensive_run_record

        def create_record_with_display_metadata(*args, **kwargs):
            record = original_create_record(*args, **kwargs)
            values = dict(_DISPLAY_METADATA.get() or {})
            customer_name = _display_literal(values.get("customer_name"), 180)
            project_name = _display_literal(values.get("project_name"), 180)
            if not customer_name and not project_name:
                return record
            identity = dict(record.get("identity") or {})
            if customer_name:
                identity["customer_name"] = customer_name
            if project_name:
                identity["project_name"] = project_name
            record["identity"] = identity
            record["integrity_sha256"] = _record_hash(record)
            return record

        create_record_with_display_metadata._nico_display_metadata_v1 = True
        run_service_module.create_comprehensive_run_record = create_record_with_display_metadata

    return {
        "intake_display_metadata_bound": True,
        "direct_start_display_metadata_bound": True,
        "display_metadata_persisted_in_initial_canonical_write": True,
        "post_create_revision_write_removed": True,
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
            for key in (
                "customer_name",
                "project_name",
                "primary_technical_contact",
                "access_method",
                "authorized_scope",
            ):
                value = _display_literal(
                    context.get(key),
                    {
                        "customer_name": 180,
                        "project_name": 180,
                        "primary_technical_contact": 600,
                        "access_method": 1200,
                        "authorized_scope": 4000,
                    }[key],
                )
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
        display = _display_state_values(canonical, spanish=spanish)
        technical, adjusted = renderer._score_pair(assessment)
        technical_text = f"{technical}/100" if technical is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
        adjusted_text = f"{adjusted}/100" if adjusted is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
        existing_client_summary = next(
            (
                stage
                for stage in stages
                if _text(stage.get("stage_id")) == "client_evidence_summary"
            ),
            {},
        )

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
        labels = {
            "customer_name": "Nombre del cliente" if spanish else "Client name",
            "project_name": "Nombre del proyecto" if spanish else "Project name",
            "primary_technical_contact": "Contacto técnico principal" if spanish else "Primary technical contact",
            "access_method": "Método de acceso" if spanish else "Access method",
            "authorized_scope": "Alcance autorizado" if spanish else "Authorized scope",
        }
        limits = {
            "customer_name": 180,
            "project_name": 180,
            "primary_technical_contact": 600,
            "access_method": 1200,
            "authorized_scope": 4000,
        }
        for key in labels:
            value = _display_literal(display.get(key), limits[key])
            client_evidence.append(
                f"{labels[key]}: {value}"
            )
        summary_evidence = [
            *client_evidence,
            *_client_summary_truth_evidence(
                canonical,
                spanish=spanish,
                technical_text=technical_text,
                adjusted_text=adjusted_text,
            ),
            *_retained_client_summary_lines(existing_client_summary.get("evidence")),
        ]
        summary_unavailable = [
            *_retained_client_summary_lines(
                existing_client_summary.get("unavailable")
                or existing_client_summary.get("limitations")
            ),
        ]
        client_summary = renderer._stage(
            "client_evidence_summary",
            "Resumen de evidencia del cliente" if spanish else "Client Evidence Summary",
            (
                "Los metadatos mostrados del cliente y del proyecto son descriptivos y no sustituyen los identificadores canónicos de alcance."
                if spanish
                else "Client and project display metadata are descriptive and do not replace canonical scope identifiers."
            ),
            evidence=summary_evidence,
            findings=existing_client_summary.get("findings") or [],
            unavailable=summary_unavailable,
            status=str(existing_client_summary.get("status") or "complete"),
        )
        # Generic report cleanup must not rewrite verified client literals.
        client_summary["evidence"] = summary_evidence
        client_summary["unavailable"] = summary_unavailable

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
