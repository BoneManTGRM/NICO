from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


VERSION = "nico.comprehensive-four-phase-report.v1"
_MARKER = "__nico_comprehensive_four_phase_report_v1__"
_SCHEMA = "nico.comprehensive-four-phase-program.v1"
_EN = "Four-Phase Assessment Program"
_ES = "Programa de evaluación en cuatro fases"


def _text(value: Any, limit: int = 2000) -> str:
    value = " ".join(str(value or "").split()).strip()
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _copy(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _spanish(canonical: Mapping[str, Any]) -> bool:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        identity.get("report_language")
        or canonical.get("report_language")
        or canonical.get("locale")
    ).casefold()
    return language.startswith("es")


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metrics(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    triage = register.get("technical_triage") if isinstance(register.get("technical_triage"), Mapping) else {}
    workload = triage.get("workload_metrics") if isinstance(triage.get("workload_metrics"), Mapping) else {}
    get = lambda key: triage.get(key) or workload.get(key) or 0
    return {
        "coverage_pct": _num(get("technical_triage_coverage_pct")),
        "completed_analyzers": int(canonical.get("completed_applicable_analyzers") or 0),
        "incomplete_analyzers": int(canonical.get("incomplete_applicable_analyzers") or 0),
        "human_review_work_units": int(get("human_review_work_units")),
        "individual_attention_candidates": int(get("candidates_requiring_individual_human_attention")),
        "grouped_review_candidates": int(get("grouped_review_eligible_candidates")),
        "grouped_review_clusters": int(get("grouped_human_review_clusters")),
    }


def build_four_phase_program(canonical: Mapping[str, Any]) -> dict[str, Any]:
    source = _copy(canonical)
    metrics = _metrics(source)
    p1 = (
        metrics["coverage_pct"] == 100.0
        and metrics["completed_analyzers"] > 0
        and metrics["incomplete_analyzers"] == 0
    )
    lifecycle = source.get("lifecycle") if isinstance(source.get("lifecycle"), Mapping) else {}
    reviewed = source.get("human_review_completed") is True
    delivery = source.get("client_delivery_allowed") is True
    state = _text(source.get("assessment_state") or "review_required").casefold()
    human_review_required = source.get("human_review_required") is not False
    explicitly_review_ready = (
        source.get("review_package_ready") is True
        or lifecycle.get("review_package_ready") is True
    )
    # The four-phase projection is published before the detached exact-artifact
    # approval supplement sets lifecycle.review_package_ready.  At that boundary,
    # a complete exact-commit triage in review_required state is already the
    # evidence that the package is ready to enter authorized human review.  Do
    # not freeze the earlier projection as NOT READY merely because the later
    # lifecycle flag has not been attached yet.
    review_ready = explicitly_review_ready or (
        p1
        and human_review_required
        and state in {"review_required", "complete", "completed"}
    )
    limitations = source.get("decision_content_limitations")
    limitations = limitations if isinstance(limitations, list) else []
    phases = [
        {
            "phase": 1,
            "id": "automated_technical_triage",
            "title_en": "Automated Technical Triage",
            "title_es": "Triaje técnico automatizado",
            "status": "complete" if p1 else "limited",
            "evidence_boundary_en": "Exact-commit scanners, candidate lineage, and proposal-only technical triage. No human disposition or approval is created.",
            "evidence_boundary_es": "Analizadores del commit exacto, linaje de candidatos y triaje técnico como propuesta. No crea disposición ni aprobación humana.",
            "metrics": metrics,
        },
        {
            "phase": 2,
            "id": "human_review_by_exception",
            "title_en": "Human Review by Exception",
            "title_es": "Revisión humana por excepción",
            "status": "complete" if reviewed else "ready_pending_human_decision" if review_ready else "not_ready",
            "evidence_boundary_en": "Individual review, homogeneous grouped work, quality-control sampling, and explicit authorized human dispositions.",
            "evidence_boundary_es": "Revisión individual, trabajo homogéneo agrupado, muestreo de control de calidad y disposiciones humanas autorizadas explícitas.",
        },
        {
            "phase": 3,
            "id": "broader_professional_assessment",
            "title_en": "Broader Professional Assessment",
            "title_es": "Evaluación profesional ampliada",
            "status": "complete_with_disclosed_limitations" if state in {"review_required", "complete", "completed"} else "limited",
            "evidence_boundary_en": "Functional QA, platform parity, requirements, stakeholder alignment, roadmap, staffing, and executive conclusions remain evidence-bound.",
            "evidence_boundary_es": "QA funcional, paridad de plataformas, requisitos, alineación, hoja de ruta, personal y conclusiones siguen limitados por evidencia.",
            "disclosed_limitation_count": len(limitations),
        },
        {
            "phase": 4,
            "id": "approval_and_client_delivery",
            "title_en": "Approval and Client Delivery",
            "title_es": "Aprobación y entrega al cliente",
            "status": "authorized" if delivery else "blocked_pending_authorized_human_approval",
            "evidence_boundary_en": "Exact-artifact approval, residual-risk acceptance, immutable receipts, and protected delivery remain authorized human actions.",
            "evidence_boundary_es": "La aprobación del artefacto exacto, la aceptación del riesgo residual, los recibos inmutables y la entrega protegida son acciones humanas autorizadas.",
        },
    ]
    return {
        "artifact_schema": _SCHEMA,
        "product": "NICO Comprehensive",
        "phase_count": 4,
        "phases": phases,
        "one_public_product": True,
        "one_client_report": True,
        "human_review_required": human_review_required,
        "human_approval_completed": reviewed,
        "client_delivery_allowed": delivery,
    }


def apply_four_phase_program(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = _copy(canonical)
    program = build_four_phase_program(output)
    output["four_phase_program"] = program
    assessment = _copy(output.get("assessment"))
    assessment["four_phase_program"] = deepcopy(program)
    output["assessment"] = assessment
    contract = _copy(output.get("v2_pipeline_contract"))
    contract.update(
        {
            "four_phase_report_version": VERSION,
            "four_phase_program_in_json": True,
            "four_phase_program_in_markdown": True,
            "four_phase_program_in_html": True,
            "four_phase_program_in_pdf": True,
            "one_comprehensive_report_with_all_four_phases": True,
            "phase4_human_approval_boundary_preserved": True,
        }
    )
    output["v2_pipeline_contract"] = contract
    return output


def _status(status: str, spanish: bool) -> str:
    labels = {
        "complete": ("COMPLETE", "COMPLETA"),
        "limited": ("LIMITED", "LIMITADA"),
        "ready_pending_human_decision": (
            "READY FOR REVIEW - HUMAN DISPOSITIONS PENDING",
            "LISTA PARA REVISIÓN - DISPOSICIONES HUMANAS PENDIENTES",
        ),
        "not_ready": ("NOT READY", "NO LISTA"),
        "complete_with_disclosed_limitations": ("COMPLETE - LIMITATIONS DISCLOSED", "COMPLETA - LIMITACIONES DECLARADAS"),
        "blocked_pending_authorized_human_approval": ("BLOCKED - AUTHORIZED HUMAN APPROVAL REQUIRED", "BLOQUEADA - REQUIERE APROBACIÓN HUMANA AUTORIZADA"),
        "authorized": ("AUTHORIZED", "AUTORIZADA"),
    }
    return labels.get(status, (status.upper(), status.upper()))[1 if spanish else 0]


def four_phase_markdown(canonical: Mapping[str, Any], *, spanish: bool | None = None) -> str:
    spanish = _spanish(canonical) if spanish is None else spanish
    program = canonical.get("four_phase_program")
    program = program if isinstance(program, Mapping) else build_four_phase_program(canonical)
    rows = [
        f"## {_ES if spanish else _EN}",
        "",
        "| Fase | Alcance | Estado | Límite de evidencia |" if spanish else "| Phase | Scope | Status | Evidence boundary |",
        "|---:|---|---|---|",
    ]
    for phase in program.get("phases") or []:
        title = phase.get("title_es" if spanish else "title_en")
        boundary = phase.get("evidence_boundary_es" if spanish else "evidence_boundary_en")
        rows.append(
            f"| {phase.get('phase')} | {_text(title).replace('|', '/')} | "
            f"{_status(_text(phase.get('status')), spanish).replace('|', '/')} | "
            f"{_text(boundary, 500).replace('|', '/')} |"
        )
    rows += [
        "",
        "**BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA**"
        if spanish
        else "**AUTOMATED DRAFT · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED**",
        "",
    ]
    return "\n".join(rows)


def repair_four_phase_markdown(markdown: str, canonical: Mapping[str, Any], *, spanish: bool | None = None) -> str:
    headings = {f"## {_EN}", f"## {_ES}"}
    output: list[str] = []
    skipping = False
    for line in str(markdown or "").splitlines():
        if line.strip() in headings:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            output.append(line)
    section = four_phase_markdown(canonical, spanish=spanish).rstrip().splitlines()
    insert = next((index for index, line in enumerate(output) if index and line.startswith("## ")), len(output))
    output[insert:insert] = [*section, ""]
    return "\n".join(output).strip() + "\n"



__all__ = [
    "VERSION",
    "_EN",
    "_ES",
    "_copy",
    "_spanish",
    "_status",
    "_text",
    "apply_four_phase_program",
    "build_four_phase_program",
    "four_phase_markdown",
    "repair_four_phase_markdown",
]
