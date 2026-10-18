from __future__ import annotations

"""Provisional work packages bound to final report records, never to section scores."""

import hashlib
import json
from collections.abc import Mapping
from nico.report_json_copy import deepcopy
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


def _identity_mismatch(record: Mapping[str, Any], binding: Mapping[str, str]) -> bool:
    declared = {
        "commit_sha": _text(record.get("source_commit_sha") or record.get("commit_sha")),
        "run_id": _text(record.get("run_id")),
        "repository": _text(record.get("repository")),
    }
    return any(value and value != binding[key] for key, value in declared.items())


def _has_projected_field(line: Any, fields: set[str]) -> bool:
    # _stage_summary retains structured-field paths before the first colon.
    # Match the path only; supplied prose must never be filtered by its content.
    path = str(line).partition(":")[0]
    return any(part.partition("[")[0] in fields for part in path.split("."))


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


_PACKAGE_PROSE = {'finding_review_and_remediation': {'action': ('Validate the retained finding; implement its retained '
                                               'correction only when the disposition and change scope '
                                               'authorize remediation.',
                                               'Validar el hallazgo conservado; aplicar su corrección '
                                               'conservada únicamente cuando la disposición y el alcance del '
                                               'cambio autoricen la remediación.'),
                                    'rationale': ('The proposal addresses this retained finding and '
                                                  'preserves its current review state.',
                                                  'La propuesta atiende este hallazgo conservado y mantiene '
                                                  'su estado actual de revisión.'),
                                    'verification': ('Retain the exact remediation revision, the '
                                                     'finding-specific verification evidence, and regression '
                                                     'results; obtain the required specialist disposition.',
                                                     'Conservar la revisión exacta de remediación, la '
                                                     'evidencia de verificación específica del hallazgo y '
                                                     'los resultados de regresión; obtener la disposición '
                                                     'profesional requerida.')},
 'evidence_gap_resolution': {'action': ('Obtain the specified missing input within authorized scope and '
                                        'assess the limitation again; absence is not a confirmed '
                                        'vulnerability.',
                                        'Obtener el insumo faltante especificado dentro del alcance '
                                        'autorizado y reevaluar la limitación; su ausencia no constituye una '
                                        'vulnerabilidad confirmada.'),
                             'rationale': ('This retained evidence gap limits the supported conclusion.',
                                           'Esta brecha de evidencia conservada limita la conclusión '
                                           'sustentada.'),
                             'verification': ('Bind the supplied evidence to its source and run, check its '
                                              'adequacy, and retain the revised limitation and review '
                                              'decision.',
                                              'Vincular la evidencia aportada con su fuente y ejecución, '
                                              'comprobar su suficiencia y conservar la limitación revisada y '
                                              'la decisión de revisión.')},
 'candidate_disposition': {'action': ('Review the retained scanner candidates and record evidence-linked '
                                      'dispositions; candidate counts are not confirmed defect counts.',
                                      'Revisar los candidatos conservados de los analizadores y registrar '
                                      'disposiciones vinculadas a evidencia; los recuentos de candidatos no '
                                      'son recuentos de defectos confirmados.'),
                           'rationale': ('The retained candidate summary records unresolved professional '
                                         'review work.',
                                         'El resumen de candidatos conservado registra trabajo de revisión '
                                         'profesional pendiente.'),
                           'verification': ('Reconcile each required disposition with the retained candidate '
                                            'population and preserve independent QC where required.',
                                            'Conciliar cada disposición requerida con la población de '
                                            'candidatos conservada y mantener el control de calidad '
                                            'independiente donde corresponda.')}}

def _package_prose(kind: str, spanish: bool) -> dict[str, str]:
    return {field: values[int(spanish)] for field, values in _PACKAGE_PROSE[kind].items()}


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
            **_package_prose("finding_review_and_remediation", spanish),
        })
        packages.append(item)

    # Only explicit retained gap records are inputs. Do not infer gaps from scores.
    gap_groups: dict[str, dict[str, Any]] = {}
    omitted_gaps: list[dict[str, Any]] = []
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
            if _identity_mismatch(stage, binding) or _identity_mismatch(gap, binding):
                omitted_gaps.append({**ref, "reason": "gap_source_identity_mismatch"})
                continue
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
            **_package_prose("evidence_gap_resolution", spanish),
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
            **_package_prose("candidate_disposition", spanish),
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
        "omitted_gap_refs": sorted(omitted_gaps, key=lambda row: (row["stage_id"], row["evidence_type"], row["record_sha256"])),
    }
    output["roadmap"] = deepcopy(packages)
    output["roadmap_truth"] = deepcopy(truth)
    assessment = deepcopy(dict(output.get("assessment") or {}))
    assessment["roadmap"] = deepcopy(packages)
    assessment["roadmap_truth"] = deepcopy(truth)
    output["assessment"] = assessment

    presentation = _roadmap_presentation(packages, spanish)
    roles = presentation["roles"]
    for stage in output.get("stage_summaries") or []:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage_id") == "six_month_roadmap":
            planning_inputs = [line for line in stage.get("evidence") or [] if _has_projected_field(line, {"constraints", "requirements"})]
            stage.update({"summary": presentation["summary"], "evidence": [*presentation["roadmap"], *planning_inputs], "roadmap": deepcopy(packages), "roadmap_truth": deepcopy(truth)})
        elif stage.get("stage_id") == "staffing_sequencing_and_cost":
            capacity_inputs = [line for line in stage.get("evidence") or [] if _has_projected_field(line, {"client_capacity_inputs_state", "supplied_capacity_constraints"})]
            stage.update({"summary": presentation["summary"], "evidence": [*presentation["staffing"], *capacity_inputs], "suggested_role_types": roles, "source_package_ids": [item["package_id"] for item in packages]})
        elif stage.get("stage_id") == "risk_reduction_and_executive_briefing":
            retained = [line for line in stage.get("evidence") or [] if not _has_projected_field(line, {"quick_wins", "medium_term_actions", "recommended_roles"})]
            stage.update({"evidence": [*retained, *presentation["executive"]], "source_package_ids": [item["package_id"] for item in packages], "suggested_role_types": roles})
    return output

def _roadmap_presentation(
    packages: list[dict[str, Any]], spanish: bool, *, retained_literal_fallback: bool = False,
) -> dict[str, Any]:
    def display(value: Any, field: str) -> str:
        try:
            return _display(value, field, spanish)
        except ValueError:
            if not retained_literal_fallback:
                raise
            # A comparison against known generated copy must not require a new
            # translation of native retained input. Keep unmatched literals; the
            # ordinary target renderer's translation checks remain unchanged.
            return _display(value, field, False)

    role_names = {
        "architecture_engineering": ("Architecture / engineering", "Arquitectura / ingeniería"),
        "cybersecurity_specialist": ("Cybersecurity specialist", "Especialista en ciberseguridad"),
        "platform_engineering": ("Platform engineering", "Ingeniería de plataforma"),
        "authorized_technical_specialist": ("Authorized technical specialist", "Especialista técnico autorizado"),
        "authorized_evidence_custodian": ("Authorized evidence custodian", "Custodio autorizado de evidencia"),
    }
    dependency_names = {
        "qualified_specialist_disposition": ("Qualified specialist disposition", "Disposición de un especialista cualificado"),
        "authorized_change_scope": ("Authorized change scope", "Alcance autorizado del cambio"),
        "authorized_input_scope": ("Authorized input scope", "Alcance autorizado del insumo"),
        "evidence_source_availability": ("Evidence source availability", "Disponibilidad de la fuente de evidencia"),
        "retained_scanner_artifact_availability": ("Retained scanner artifact availability", "Disponibilidad del artefacto conservado del analizador"),
        "qualified_specialist_review": ("Qualified specialist review", "Revisión de un especialista cualificado"),
    }
    gap_labels = {
        "review_candidate_summary": ("Candidate review summary", "Resumen de revisión de candidatos"),
        "runtime_functional_qa": ("Runtime functional QA", "QA funcional en ejecución"),
        "authoritative_requirements": ("Authoritative requirements", "Requisitos autorizados"),
        "device_runtime_parity": ("Device runtime parity", "Paridad de dispositivos en ejecución"),
        "stakeholder_business_authority": ("Stakeholder and business authority", "Autoridad de partes interesadas y negocio"),
        "incident_and_recovery_history": ("Incident and recovery history", "Historial de incidentes y recuperación"),
    }
    details: list[str] = []
    for item in packages:
        label = item.get("finding_id") or item.get("evidence_type") or "review_candidate_summary"
        display_label = _copy(*gap_labels[label], spanish) if label in gap_labels else str(label)
        prefix = item["package_id"] + " | " + display_label
        details.append(prefix + " | " + item["action"])
        correction = item.get("retained_correction") or item.get("retained_required_input")
        if correction:
            details.append(prefix + " | " + display(correction, "recommendation"))
        if item.get("retained_rationale"):
            details.append(prefix + " | " + display(item["retained_rationale"], "why_it_matters"))
        details.append(prefix + " | " + item["verification"])
        if item.get("retained_verification"):
            details.append(prefix + " | " + display(item["retained_verification"], "verification"))
        details.append(prefix + " | " + _copy("Suggested role type", "Tipo de función sugerida", spanish) + ": " + _copy(*role_names[item["suggested_role_type"]], spanish) + " | " + _copy("Dependencies", "Dependencias", spanish) + ": " + ", ".join(_copy(*dependency_names[dep["gate"]], spanish) for dep in item["dependencies"]))
    boundary = _copy("Work packages are provisional and bound to retained findings or evidence gaps. The 0-30/31-90/91-180 windows are illustrative; no owner, capacity, cost, date, approval, or delivery commitment is created.", "Los paquetes de trabajo son provisionales y están vinculados a hallazgos conservados o brechas de evidencia. Las ventanas 0-30/31-90/91-180 son ilustrativas; no se crea compromiso de responsable, capacidad, costo, fecha, aprobación ni entrega.", spanish)
    no_work = _copy("No retained finding or explicit evidence gap supports a work package; an empty planning window does not establish a clean assessment.", "Ningún hallazgo conservado ni brecha de evidencia explícita sustenta un paquete de trabajo; una ventana de planificación vacía no establece una evaluación sin hallazgos.", spanish)
    roles = sorted({item["suggested_role_type"] for item in packages})
    role_lines = [_copy("Suggested role types", "Tipos de función sugeridos", spanish) + ": " + ", ".join(_copy(*role_names[role], spanish) for role in roles)] if roles else [no_work]
    shown = packages[:7]
    package_line = (_copy("Proposed work packages (summary)", "Paquetes de trabajo propuestos (resumen)", spanish)
                    + f" ({len(shown)}/{len(packages)}): " + ", ".join(item["package_id"] for item in shown))
    return {"summary": boundary, "roadmap": details or [no_work], "staffing": role_lines, "executive": [package_line if packages else no_work, boundary], "roles": roles}




def localize_retained_roadmap(canonical: Mapping[str, Any], *, spanish: bool) -> dict[str, Any]:
    """Reproject known generated copy, without deriving or rebinding any work package."""
    output = deepcopy(dict(canonical))
    truth = output.get("roadmap_truth")
    packages = output.get("roadmap")
    identity = output.get("identity") or {}
    binding = {key: _text(identity.get(key)) for key in _IDENTITY}
    if (not isinstance(truth, Mapping) or truth.get("version") != VERSION
            or not all(binding.values()) or truth.get("source_binding") != binding
            or not isinstance(packages, list) or truth.get("work_package_count") != len(packages)
            or any(not isinstance(item, dict) or item.get("kind") not in _PACKAGE_PROSE
                   or item.get("source_binding") != binding for item in packages)):
        return output

    def localized_packages(target: bool) -> list[dict[str, Any]]:
        result = deepcopy(packages)
        for item in result:
            for field, pair in _PACKAGE_PROSE[item["kind"]].items():
                if item.get(field) in pair:
                    item[field] = pair[int(target)]
        return result

    source_presentation = _roadmap_presentation(localized_packages(not spanish), not spanish, retained_literal_fallback=True)
    target_packages = localized_packages(spanish)
    target_presentation = _roadmap_presentation(target_packages, spanish, retained_literal_fallback=True)
    stage_keys = {"six_month_roadmap": "roadmap", "staffing_sequencing_and_cost": "staffing",
                  "risk_reduction_and_executive_briefing": "executive"}
    for container in (output, output.get("assessment")):
        if not isinstance(container, dict):
            continue
        if container.get("roadmap") == packages and container.get("roadmap_truth") == truth:
            container["roadmap"] = deepcopy(target_packages)
        for stage in container.get("stage_summaries") or []:
            if not isinstance(stage, dict) or stage.get("stage_id") not in stage_keys:
                continue
            # Only complete, exact generated lines are replaced. Client planning
            # inputs and unknown prose are retained; no recursive text replacement.
            key = stage_keys[stage["stage_id"]]
            translations = dict(zip(source_presentation[key], target_presentation[key], strict=True))
            if key == "executive" and packages:
                for prior_spanish in (False, True):
                    legacy = (_copy("Proposed work packages", "Paquetes de trabajo propuestos", prior_spanish)
                              + ": " + ", ".join(item["package_id"] for item in packages))
                    translations[legacy] = target_presentation[key][0]
            stage["evidence"] = [translations.get(line, line) if isinstance(line, str) else line
                                 for line in stage.get("evidence") or []]
            if stage.get("summary") == source_presentation["summary"]:
                stage["summary"] = target_presentation["summary"]
            if stage.get("roadmap") == packages and stage.get("roadmap_truth") == truth:
                stage["roadmap"] = deepcopy(target_packages)
    return output

__all__ = ["VERSION", "bind_final_finding_roadmap", "localize_retained_roadmap"]



def _validate_rebinding_sources(package, canonical, binding, by_alias):
    """Validate source contracts before any normalization-driven digest changes."""
    refs = package['source_refs']
    kind = package['kind']
    expected_surface = {
        'finding_review_and_remediation': 'canonical_findings',
        'candidate_disposition': 'review_candidate_summary',
        'evidence_gap_resolution': 'prior_stage_results',
    }[kind]
    if (any(ref.get('surface') != expected_surface for ref in refs)
            or (kind != 'evidence_gap_resolution' and len(refs) != 1)):
        raise ValueError('roadmap_rebinding_reference_kind_mismatch')
    for dependency in package['dependencies']:
        if (not isinstance(dependency, Mapping)
                or ('source_ref' in dependency and dependency['source_ref'] not in refs)):
            raise ValueError('roadmap_rebinding_dependency_reference_mismatch')
    if kind == 'finding_review_and_remediation':
        finding = by_alias.get(refs[0].get('finding_id'))
        if finding is None:
            raise ValueError('roadmap_rebinding_finding_unresolved')
        if by_alias.get(package.get('finding_id')) != finding:
            raise ValueError('roadmap_rebinding_package_finding_mismatch')
        # Check every declared field independently: a matching source_commit_sha
        # must not hide a contradictory commit_sha (or another declared source).
        for field in (*_IDENTITY, 'source_commit_sha'):
            expected = binding['commit_sha' if field == 'source_commit_sha' else field]
            if _text(finding.get(field)) and _text(finding[field]) != expected:
                raise ValueError('roadmap_rebinding_finding_source_identity_mismatch')
        if not any(dep.get('gate') == 'qualified_specialist_disposition'
                   and dep.get('source_ref') == refs[0] for dep in package['dependencies']):
            raise ValueError('roadmap_rebinding_dependency_reference_missing')
    elif kind == 'candidate_disposition':
        summary = canonical.get('review_candidate_summary')
        count = summary.get('review_required_total') if isinstance(summary, Mapping) else None
        claimed = package.get('review_required_candidate_count')
        if type(count) is not int or count <= 0 or type(claimed) is not int or claimed != count:
            raise ValueError('roadmap_rebinding_candidate_count_mismatch')

def rebind_generated_roadmap(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the entire provisional graph to reconciled findings before rendering.

    This derives a new draft graph; it does not attest that an earlier reference
    digest describes the normalized record. IDs and all generated mirrors change
    together. Frozen artifacts must never call this after their render boundary.
    """
    from nico.report_work_package_identity_v1 import is_work_package

    truth = canonical.get('roadmap_truth')
    if not isinstance(truth, Mapping) or truth.get('version') != VERSION:
        return dict(canonical)
    binding = {key: _text((canonical.get('identity') or {}).get(key)) for key in _IDENTITY}
    packages = canonical.get('roadmap')
    if (not all(binding.values()) or truth.get('source_binding') != binding
            or not isinstance(packages, list) or truth.get('work_package_count') != len(packages)):
        raise ValueError('roadmap_rebinding_source_invalid')
    for container in (canonical, canonical.get('assessment')):
        if not isinstance(container, Mapping):
            continue
        mirrors = [container, *(container.get('stage_summaries') or [])]
        for mirror in mirrors:
            if isinstance(mirror, Mapping) and 'roadmap' in mirror and mirror['roadmap'] != packages:
                raise ValueError('roadmap_rebinding_package_mirror_mismatch')
    by_alias = {}
    for finding in canonical.get('canonical_findings') or []:
        for alias in [finding.get('finding_id'), *(finding.get('finding_aliases') or [])]:
            if alias:
                if alias in by_alias and by_alias[alias] != finding:
                    raise ValueError('roadmap_rebinding_ambiguous_finding')
                by_alias[alias] = finding
    rebound = []
    for package in packages:
        if (not is_work_package(package) or package.get('source_binding') != binding
                or package.get('stakeholder_approved') is not False
                or package.get('delivery_authorized') is not False
                or package.get('package_id') != _base(binding, package['kind'], package['source_refs'])['package_id']):
            raise ValueError('roadmap_rebinding_package_invalid')
        _validate_rebinding_sources(package, canonical, binding, by_alias)
        item = deepcopy(package)
        replacements = []
        for ref in item['source_refs']:
            old = deepcopy(ref)
            if ref.get('surface') == 'canonical_findings':
                finding = by_alias.get(ref.get('finding_id'))
                if finding is None:
                    raise ValueError('roadmap_rebinding_finding_unresolved')
                # Keep the source alias: distinct proposals may reference distinct
                # aliases of one final finding. Both resolve to the final record.
                ref['record_sha256'] = _hash(finding)
                if item['kind'] == 'finding_review_and_remediation':
                    item.update({
                        'retained_disposition': _text(finding.get('disposition')),
                        'retained_status': _text(finding.get('status')),
                        'retained_severity': _text(finding.get('severity')),
                        'retained_location': _text(finding.get('exact_source') or finding.get('location') or finding.get('path')),
                        'retained_correction': deepcopy(finding.get('recommendation') or finding.get('recommended_correction') or ''),
                        'retained_verification': deepcopy(finding.get('verification') or finding.get('acceptance_criteria') or finding.get('exit_criteria') or []),
                        'retained_rationale': deepcopy(finding.get('business_impact') or finding.get('impact') or finding.get('interpretation') or ''),
                        'suggested_role_type': _role(finding),
                    })
            elif ref.get('surface') == 'review_candidate_summary':
                ref['record_sha256'] = _hash(canonical.get('review_candidate_summary') or {})
            elif ref.get('surface') != 'prior_stage_results':
                raise ValueError('roadmap_rebinding_reference_unsupported')
            replacements.append((old, deepcopy(ref)))
        for dependency in item.get('dependencies') or []:
            for old, new in replacements:
                if dependency.get('source_ref') == old:
                    dependency['source_ref'] = deepcopy(new)
        item['package_id'] = _base(binding, item['kind'], item['source_refs'])['package_id']
        rebound.append(item)
    if len({p['package_id'] for p in rebound}) != len(rebound):
        raise ValueError('roadmap_rebinding_package_collision')
    if rebound == packages:
        # Preparation can introduce planning stages after the source builder ran.
        # Derive their missing ID lists even when no package needed rebinding.
        # Keep explicit values intact: the freeze validator must reject drift.
        output = dict(canonical)
        ids = [package['package_id'] for package in packages]
        for name, container in ((None, canonical), ('assessment', canonical.get('assessment'))):
            if not isinstance(container, Mapping):
                continue
            stages = container.get('stage_summaries')
            if not isinstance(stages, list):
                continue
            missing = [(i, stage) for i, stage in enumerate(stages)
                       if isinstance(stage, Mapping)
                       and stage.get('stage_id') in {'staffing_sequencing_and_cost', 'risk_reduction_and_executive_briefing'}
                       and 'source_package_ids' not in stage]
            if missing:
                updated = list(stages)
                for index, stage in missing:
                    updated[index] = {**stage, 'source_package_ids': list(ids)}
                if name is None:
                    output['stage_summaries'] = updated
                else:
                    output[name] = {**container, 'stage_summaries': updated}
        return output
    by_id = {old['package_id']: (old, new) for old, new in zip(packages, rebound, strict=True)}
    def replace_graph(value):
        if isinstance(value, list):
            return [replace_graph(child) for child in value]
        if not isinstance(value, Mapping):
            return deepcopy(value)
        pair = by_id.get(value.get('package_id')) if isinstance(value.get('package_id'), str) else None
        if pair and is_work_package(value):
            if value != pair[0]:
                raise ValueError('roadmap_rebinding_package_mirror_mismatch')
            return deepcopy(pair[1])
        result = {key: replace_graph(child) for key, child in value.items()}
        if isinstance(value.get('source_package_ids'), list):
            result['source_package_ids'] = [by_id[item][1]['package_id'] if isinstance(item, str) and item in by_id else item
                                            for item in value['source_package_ids']]
        return result
    output = replace_graph(canonical)
    spanish = str(output.get('report_language') or '').startswith('es')
    old_presentation = _roadmap_presentation(packages, spanish, retained_literal_fallback=True)
    presentation = _roadmap_presentation(rebound, spanish, retained_literal_fallback=True)
    stage_keys = {'six_month_roadmap':'roadmap', 'staffing_sequencing_and_cost':'staffing',
                  'risk_reduction_and_executive_briefing':'executive'}
    for container in (output, output.get('assessment')):
        if not isinstance(container, dict):
            continue
        if 'roadmap' in container:
            container['roadmap'] = deepcopy(rebound)
            container['roadmap_truth'] = deepcopy(truth)
        for stage in container.get('stage_summaries') or []:
            kind = stage_keys.get(stage.get('stage_id'))
            if kind is None:
                continue
            old_lines = set(old_presentation[kind])
            retained = [line for line in stage.get('evidence') or [] if not isinstance(line, str) or line not in old_lines]
            stage['evidence'] = [*presentation[kind], *retained]
            if kind == 'roadmap':
                stage['roadmap'] = deepcopy(rebound)
                stage['roadmap_truth'] = deepcopy(truth)
            else:
                stage['source_package_ids'] = [p['package_id'] for p in rebound]
                stage['suggested_role_types'] = presentation['roles']
    return output


def assert_final_roadmap_binding(canonical: Mapping[str, Any]) -> None:
    """Refuse to freeze artifacts if normalized sources changed after rendering."""
    rebound = rebind_generated_roadmap(canonical)
    if rebound.get('roadmap') != canonical.get('roadmap'):
        raise ValueError('roadmap_binding_changed_after_render')
    truth = canonical.get('roadmap_truth')
    if not isinstance(truth, Mapping) or truth.get('version') != VERSION:
        return
    packages = canonical['roadmap']
    ids = [p['package_id'] for p in packages]
    for container in (canonical, canonical.get('assessment')):
        if not isinstance(container, Mapping):
            continue
        if container.get('roadmap') != packages or container.get('roadmap_truth') != truth:
            raise ValueError('roadmap_final_mirror_mismatch')
        for stage in container.get('stage_summaries') or []:
            if stage.get('stage_id') == 'six_month_roadmap':
                if stage.get('roadmap') != packages or stage.get('roadmap_truth') != truth:
                    raise ValueError('roadmap_final_mirror_mismatch')
            elif stage.get('stage_id') in {'staffing_sequencing_and_cost', 'risk_reduction_and_executive_briefing'}:
                if stage.get('source_package_ids') != ids:
                    raise ValueError('roadmap_final_dependent_ids_mismatch')
