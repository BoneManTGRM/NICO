from __future__ import annotations

"""Provisional work packages bound to final report records, never to section scores."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_finding_roadmap.v1"
_IDENTITY = ("run_id", "repository", "commit_sha", "evidence_ledger_id")
_CLOSED = {"resolved", "fixed", "false_positive", "not_applicable", "excluded", "accepted_risk"}
_GAP_CLOSED = _CLOSED | {"complete", "completed", "verified", "supplied"}
_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3, "info": 4, "informational": 4}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _copy(en: str, es: str, spanish: bool) -> str:
    return es if spanish else en


def _display(value: Any, field: str, spanish: bool) -> str:
    if isinstance(value, (list, tuple)):
        return "; ".join(_display(item, field, spanish) for item in value if item)
    text = _text(value)
    if spanish and text:
        from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
        return _translate_presentation_field(text, field)
    return text


def _role(finding: Mapping[str, Any]) -> str:
    category = _text(finding.get("category") or finding.get("finding_family")).casefold()
    if any(word in category for word in ("architecture", "complexity", "maintainability")):
        return "architecture_engineering"
    if any(word in category for word in ("security", "dependency", "secret")):
        return "cybersecurity_specialist"
    if any(word in category for word in ("ci_cd", "deployment", "infrastructure")):
        return "platform_engineering"
    return "authorized_technical_specialist"


def _base(binding: Mapping[str, str], kind: str, refs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "package_id": "NICO-WORK-" + _hash({"binding": binding, "kind": kind, "refs": refs})[:16].upper(),
        "kind": kind,
        "source_binding": dict(binding),
        "source_refs": deepcopy(refs),
        "sequence_state": "nico_proposed",
        "execution_state": "not_started",
        "stakeholder_approved": False,
        "assigned_owner": None,
        "committed_date": None,
        "capacity_estimate": None,
        "cost_estimate": None,
        "delivery_authorized": False,
    }


def bind_final_finding_roadmap(canonical: Mapping[str, Any], *, raw_stages: Mapping[str, Any]) -> dict[str, Any]:
    """Derive new report projections after restoration, leaving retained input untouched.

    Record digests and report identity bind each proposal to its actual source. A
    candidate is review work, a missing input is evidence work, and neither becomes
    a confirmed defect. Illustrative planning windows never manufacture work.
    """
    output = deepcopy(dict(canonical))
    identity = output.get("identity") if isinstance(output.get("identity"), Mapping) else {}
    binding = {key: _text(identity.get(key)) for key in _IDENTITY}
    if not all(binding.values()):
        raise ValueError("roadmap_source_identity_incomplete")
    spanish = str(output.get("report_language") or identity.get("report_language") or "").startswith("es")
    packages: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    findings = [row for row in output.get("canonical_findings") or [] if isinstance(row, Mapping)]
    for finding in findings:
        finding_id = _text(finding.get("finding_id") or finding.get("id"))
        reference = {"surface": "canonical_findings", "finding_id": finding_id, "record_sha256": _hash(finding)}
        disposition = _text(finding.get("disposition"))
        status = _text(finding.get("status"))
        declared_sha = _text(finding.get("source_commit_sha") or finding.get("commit_sha"))
        declared_run = _text(finding.get("run_id"))
        declared_repo = _text(finding.get("repository"))
        reason = ""
        if not finding_id:
            reason = "stable_finding_identity_unavailable"
        elif declared_sha and declared_sha != binding["commit_sha"]:
            reason = "finding_source_commit_mismatch"
        elif (declared_run and declared_run != binding["run_id"]) or (declared_repo and declared_repo != binding["repository"]):
            reason = "finding_source_identity_mismatch"
        elif disposition.casefold() in _CLOSED or status.casefold() in _CLOSED:
            reason = "retained_disposition_does_not_request_remediation"
        if reason:
            omitted.append({**reference, "reason": reason})
            continue
        item = _base(binding, "finding_review_and_remediation", [reference])
        item.update({
            "finding_id": finding_id,
            "retained_disposition": disposition,
            "retained_status": status,
            "retained_severity": _text(finding.get("severity")),
            "retained_location": _text(finding.get("exact_source") or finding.get("location") or finding.get("path")),
            "retained_correction": deepcopy(finding.get("recommendation") or finding.get("recommended_correction") or ""),
            "retained_verification": deepcopy(finding.get("verification") or finding.get("acceptance_criteria") or finding.get("exit_criteria") or []),
            "retained_rationale": deepcopy(finding.get("business_impact") or finding.get("impact") or finding.get("interpretation") or ""),
            "evidence_scope": "retained_canonical_record",
            "suggested_role_type": _role(finding),
            "dependencies": [{"gate": "qualified_specialist_disposition", "source_ref": reference}, {"gate": "authorized_change_scope"}],
            "action": _copy("Validate the retained finding; implement its retained correction only when the disposition and change scope authorize remediation.", "Validar el hallazgo conservado; aplicar su corrección conservada únicamente cuando la disposición y el alcance del cambio autoricen la remediación.", spanish),
            "rationale": _copy("The proposal addresses this retained finding and preserves its current review state.", "La propuesta atiende este hallazgo conservado y mantiene su estado actual de revisión.", spanish),
            "verification": _copy("Retain the exact remediation revision, the finding-specific verification evidence, and regression results; obtain the required specialist disposition.", "Conservar la revisión exacta de remediación, la evidencia de verificación específica del hallazgo y los resultados de regresión; obtener la disposición profesional requerida.", spanish),
        })
        packages.append(item)

    # Only explicit retained gap records are inputs. Do not infer gaps from scores.
    gap_groups: dict[str, dict[str, Any]] = {}
    for stage_id, stage in sorted(raw_stages.items()):
        if not isinstance(stage, Mapping) or _text(stage.get("status")).casefold() in {"excluded", "not_applicable"}:
            continue
        for gap in stage.get("missing_evidence") or []:
            if not isinstance(gap, Mapping) or _text(gap.get("state")).casefold() in _GAP_CLOSED:
                continue
            kind = _text(gap.get("evidence_type"))
            if not kind:
                continue
            digest = _hash(gap)
            ref = {"surface": "prior_stage_results", "stage_id": str(stage_id), "field": "missing_evidence", "evidence_type": kind, "record_sha256": digest}
            group = gap_groups.setdefault(digest, {"gap": gap, "refs": []})
            group["refs"].append(ref)
    for digest in sorted(gap_groups):
        gap, refs = gap_groups[digest]["gap"], gap_groups[digest]["refs"]
        item = _base(binding, "evidence_gap_resolution", refs)
        item.update({
            "evidence_type": _text(gap.get("evidence_type")),
            "retained_state": _text(gap.get("state")) or "unknown",
            "retained_required_input": deepcopy(gap.get("evidence_to_resolve") or ""),
            "retained_rationale": deepcopy(gap.get("why_it_matters") or gap.get("cannot_conclude") or ""),
            "evidence_scope": "retained_gap_record",
            "suggested_role_type": "authorized_evidence_custodian",
            "dependencies": [{"gate": "authorized_input_scope"}, {"gate": "evidence_source_availability"}],
            "action": _copy("Obtain the specified missing input within authorized scope and assess the limitation again; absence is not a confirmed vulnerability.", "Obtener el insumo faltante especificado dentro del alcance autorizado y reevaluar la limitación; su ausencia no constituye una vulnerabilidad confirmada.", spanish),
            "rationale": _copy("This retained evidence gap limits the supported conclusion.", "Esta brecha de evidencia conservada limita la conclusión sustentada.", spanish),
            "verification": _copy("Bind the supplied evidence to its source and run, check its adequacy, and retain the revised limitation and review decision.", "Vincular la evidencia aportada con su fuente y ejecución, comprobar su suficiencia y conservar la limitación revisada y la decisión de revisión.", spanish),
        })
        packages.append(item)

    summary = output.get("review_candidate_summary") if isinstance(output.get("review_candidate_summary"), Mapping) else {}
    count = summary.get("review_required_total")
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        ref = {"surface": "review_candidate_summary", "record_sha256": _hash(summary)}
        item = _base(binding, "candidate_disposition", [ref])
        item.update({
            "review_required_candidate_count": count,
            "evidence_scope": "retained_candidate_summary",
            "suggested_role_type": "cybersecurity_specialist",
            "dependencies": [{"gate": "retained_scanner_artifact_availability"}, {"gate": "qualified_specialist_review"}],
            "action": _copy("Review the retained scanner candidates and record evidence-linked dispositions; candidate counts are not confirmed defect counts.", "Revisar los candidatos conservados de los analizadores y registrar disposiciones vinculadas a evidencia; los recuentos de candidatos no son recuentos de defectos confirmados.", spanish),
            "rationale": _copy("The retained candidate summary records unresolved professional review work.", "El resumen de candidatos conservado registra trabajo de revisión profesional pendiente.", spanish),
            "verification": _copy("Reconcile each required disposition with the retained candidate population and preserve independent QC where required.", "Conciliar cada disposición requerida con la población de candidatos conservada y mantener el control de calidad independiente donde corresponda.", spanish),
        })
        packages.append(item)

    rank = {"finding_review_and_remediation": 0, "candidate_disposition": 1, "evidence_gap_resolution": 2}
    packages.sort(key=lambda item: (rank[item["kind"]], _SEVERITY.get(item.get("retained_severity", "").casefold(), 5), item["package_id"]))
    for index, item in enumerate(packages, 1):
        item["advisory_order"] = index
        item["ordering_basis"] = "advisory_priority_only_dependencies_are_explicit"
    truth = {
        "version": VERSION,
        "binding_boundary": "after_final_canonical_finding_reconciliation",
        "source_binding": binding,
        "work_package_count": len(packages),
        "framework_only": not bool(packages),
        "illustrative_windows": ["0-30 days", "31-90 days", "91-180 days"],
        "windows_are_commitments": False,
        "window_allocation": "unassigned_pending_authorized_planning",
        "nico_proposed_sequence": True,
        "stakeholder_approved_sequence": False,
        "approved_dates_present": False,
        "commercial_values_generated": False,
        "confirmed_defects_inferred_from_candidates_or_gaps": False,
        "omitted_finding_refs": sorted(omitted, key=lambda row: (row.get("finding_id", ""), row["record_sha256"])),
    }
    output["roadmap"] = deepcopy(packages)
    output["roadmap_truth"] = deepcopy(truth)
    assessment = deepcopy(dict(output.get("assessment") or {}))
    assessment["roadmap"] = deepcopy(packages)
    assessment["roadmap_truth"] = deepcopy(truth)
    output["assessment"] = assessment

    details: list[str] = []
    for item in packages:
        label = item.get("finding_id") or item.get("evidence_type") or "review_candidate_summary"
        prefix = item["package_id"] + " | " + str(label)
        details.append(prefix + " | " + item["action"])
        correction = item.get("retained_correction") or item.get("retained_required_input")
        if correction:
            details.append(prefix + " | " + _display(correction, "recommendation", spanish))
        if item.get("retained_rationale"):
            details.append(prefix + " | " + _display(item["retained_rationale"], "why_it_matters", spanish))
        details.append(prefix + " | " + item["verification"])
        if item.get("retained_verification"):
            details.append(prefix + " | " + _display(item["retained_verification"], "verification", spanish))
        details.append(prefix + " | " + _copy("Suggested role type", "Tipo de función sugerida", spanish) + ": " + item["suggested_role_type"] + " | " + _copy("Dependencies", "Dependencias", spanish) + ": " + ", ".join(dep["gate"] for dep in item["dependencies"]))
    boundary = _copy("Work packages are provisional and bound to retained findings or evidence gaps. The 0-30/31-90/91-180 windows are illustrative; no owner, capacity, cost, date, approval, or delivery commitment is created.", "Los paquetes de trabajo son provisionales y están vinculados a hallazgos conservados o brechas de evidencia. Las ventanas 0-30/31-90/91-180 son ilustrativas; no se crea compromiso de responsable, capacidad, costo, fecha, aprobación ni entrega.", spanish)
    no_work = _copy("No retained finding or explicit evidence gap supports a work package; an empty planning window does not establish a clean assessment.", "Ningún hallazgo conservado ni brecha de evidencia explícita sustenta un paquete de trabajo; una ventana de planificación vacía no establece una evaluación sin hallazgos.", spanish)
    roles = sorted({item["suggested_role_type"] for item in packages})
    for stage in output.get("stage_summaries") or []:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage_id") == "six_month_roadmap":
            stage.update({"summary": boundary, "evidence": details or [no_work], "roadmap": deepcopy(packages), "roadmap_truth": deepcopy(truth)})
        elif stage.get("stage_id") == "staffing_sequencing_and_cost":
            stage.update({"summary": boundary, "evidence": [_copy("Suggested role types", "Tipos de función sugeridos", spanish) + ": " + ", ".join(roles)] if roles else [no_work], "suggested_role_types": roles, "source_package_ids": [item["package_id"] for item in packages]})
    return output


__all__ = ["VERSION", "bind_final_finding_roadmap"]
