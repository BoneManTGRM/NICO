"""Renderer-local coverage labels; never alter the retained source populations."""
from collections import Counter
from typing import Any, Mapping


def stage_preview_labels(stage: Mapping[str, Any], context: Mapping[str, Any], *,
                         evidence_limit: int | None = None,
                         evidence_text_limit: int | None = None,
                         findings_limit: int | None = None,
                         spanish: bool = False) -> list[str]:
    assessment = context.get('assessment')
    presentation_source = context.get('_preview_context')
    sources = [presentation_source if isinstance(presentation_source, Mapping) else {},
               context, assessment if isinstance(assessment, Mapping) else {}, stage]

    def retained(key: str) -> list[Mapping[str, Any]] | None:
        for source in sources:
            value = source.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return None

    stage_id = stage.get('stage_id')
    if stage_id == 'dependency_security_static_analysis':
        report = stage.get('_repeatability_assurance')
        if not isinstance(report, Mapping):
            return []
        analyzers = report.get('analyzers')
        if not isinstance(analyzers, list):
            return []
        lines = [('La finalización de la ejecución y la garantía de repetibilidad son distintas. '
                  'La repetibilidad exige las pasadas consecutivas con SHA exacto indicadas; '
                  'una ejecución completa no satisface por sí sola ese requisito.') if spanish else
                 ('Execution completion and repeatability assurance are separate. '
                  'Repeatability requires the stated consecutive exact-SHA passes; '
                  'one completed execution alone does not satisfy that requirement.')]
        for item in analyzers:
            if not isinstance(item, Mapping) or item.get('required') is not True:
                continue
            observed, required = item.get('consecutive_successful_passes'), item.get('consecutive_passes_required')
            if type(observed) is not int or type(required) is not int or observed < 0 or required < 1:
                continue
            name = str(item.get('scanner') or 'unknown')
            state = ('requisito satisfecho' if item.get('acceptance_ready') is True else 'requisito no satisfecho') if spanish else ('requirement met' if item.get('acceptance_ready') is True else 'requirement not met')
            lines.append((f'{name}: pasadas consecutivas con SHA exacto {observed}/{required}; {state}.' if spanish else
                          f'{name}: consecutive exact-SHA passes {observed}/{required}; {state}.'))
        return lines
    if stage_id == 'risk_reduction_and_executive_briefing':
        packages = retained('roadmap')
        # The producer binds these IDs to this stage's executive evidence.
        # An explicit empty list is authoritative; only absence uses outer data.
        source_ids = stage.get('source_package_ids')
        if packages is None and not isinstance(source_ids, list):
            return []
        identifiers = ({str(value) for value in source_ids if value}
                       if isinstance(source_ids, list) else
                       {str(item['package_id']) for item in packages or [] if item.get('package_id')})
        for line in list(stage.get('evidence') or [])[:evidence_limit]:
            if str(line).startswith(('Proposed work packages (summary)', 'Paquetes de trabajo propuestos (resumen)')):
                shown = set(str(line).partition(': ')[2].split(', ')) & identifiers
                return [(f'Vista previa de identificadores de paquetes de trabajo: {len(shown)} de {len(identifiers)}.'
                         if spanish else f'Work-package ID preview: {len(shown)} of {len(identifiers)}.')]
        return []
    if stage_id == 'review_required_candidate_register':
        complete = None
        render_count = None
        for source in sources:
            nested = source.get('assessment')
            for candidate_source in (source, nested if isinstance(nested, Mapping) else {}):
                register = candidate_source.get('canonical_scanner_finding_register')
                count = register.get('_render_population_count') if isinstance(register, Mapping) else None
                compact = (type(count) is int and count > 0
                           and count == register.get('candidate_record_count')
                           and register.get('count_parity_verified') is True) if isinstance(register, Mapping) else False
                if isinstance(register, Mapping) and (isinstance(register.get('findings'), list) or compact):
                    complete = register.get('findings', [])
                    count = register.get('_render_population_count')
                    if (not complete and type(count) is int and count > 0
                            and count == register.get('candidate_record_count')
                            and register.get('count_parity_verified') is True):
                        render_count = count
                    break
            if complete is not None:
                break
        # Legacy projections can retain a bounded preview without the canonical
        # register. Its known population is still useful, but is not proof of
        # the complete candidate population or a complete-register location.
        preview = retained('review_candidate_register')
        population = complete if complete is not None else preview
        total = (str(render_count) if render_count is not None else
                 str(len(population)) if population is not None else ('desconocido' if spanish else 'unknown'))
        rows = [line for line in stage.get('findings') or [] if str(line or '').strip()][:findings_limit]
        reference = 'assessment.canonical_scanner_finding_register.findings'
        if spanish:
            suffix = (f'Registro completo: {reference} en el JSON canónico.' if complete is not None
                      else 'Registro completo no disponible en esta proyección; el total corresponde solo a la vista previa conservada.')
            return [f'Vista previa del registro de candidatos: {len(rows)} de {total} registros conservados. ' + suffix]
        suffix = (f'Complete register: {reference} in canonical JSON.' if complete is not None
                  else 'Complete register unavailable in this projection; total describes only the retained preview.')
        return [f'Candidate register preview: {len(rows)} of {total} retained records. ' + suffix]
    if stage_id != 'six_month_roadmap':
        return []
    # Count the collection that produced the rendered details, not an older
    # outer projection. Legacy stages without a collection keep the fallback.
    stage_packages = stage.get('roadmap')
    packages = ([item for item in stage_packages if isinstance(item, Mapping)]
                if isinstance(stage_packages, list) else retained('roadmap'))
    package_ids = {str(item['package_id']) for item in packages or [] if item.get('package_id')}
    lines = [' '.join(str(line).split()) for line in stage.get('evidence') or [] if str(line or '').strip()]
    # The roadmap producer prefixes each detail with the exact retained package ID.
    def counts(values: list[str]) -> Counter:
        return Counter(line.partition(' | ')[0] for line in values
                       if line.partition(' | ')[0] in package_ids)
    complete, shown = counts(lines), counts(lines[:evidence_limit])
    total = str(len(package_ids)) if packages is not None else ('desconocido' if spanish else 'unknown')
    partial = any(count < complete[identifier] for identifier, count in shown.items())
    if evidence_text_limit is not None:
        # Match the PDF bullet renderer's whitespace normalization before its
        # character cap. A present row is not necessarily a complete detail.
        partial = partial or any(
            line.partition(' | ')[0] in package_ids
            and len(line) > evidence_text_limit
            for line in lines[:evidence_limit]
        )
    if spanish:
        label = f'Vista previa de la hoja de ruta: detalles de {len(shown)} de {total} paquetes de trabajo.'
        if partial:
            label += ' Algunos paquetes se muestran parcialmente.'
        return [label + ' Detalles completos: roadmap en el JSON canónico.']
    label = f'Roadmap preview: details from {len(shown)} of {total} work packages.'
    if partial:
        label += ' Some packages are partially shown.'
    return [label + ' Complete details: roadmap in canonical JSON.']


def retained_coverage_disclosures(context: Mapping[str, Any], *, spanish: bool) -> list[str]:
    """Final client-summary disclosures from retained typed data, without mutation."""
    lines: list[str] = []
    assessment = context.get('assessment')
    assessment = assessment if isinstance(assessment, Mapping) else {}
    register = assessment.get('canonical_scanner_finding_register')
    if isinstance(register, Mapping) and isinstance(register.get('findings'), list):
        count = len(register['findings'])
        path = 'assessment.canonical_scanner_finding_register.findings'
        lines.append((f'Registro completo de candidatos: {count} registros conservados; {path} en el JSON canónico.'
                      if spanish else f'Complete candidate register: {count} retained records; {path} in canonical JSON.'))
    investigation = (register.get('final_candidate_investigation') if 'final_candidate_investigation' in register else register.get('candidate_investigation')) if isinstance(register, Mapping) else None
    if isinstance(investigation, Mapping):
        count = investigation.get('candidate_count')
        completed = investigation.get('bounded_rule_analysis_completed')
        calls = investigation.get('model_invocations')
        if (type(count) is int and type(completed) is int and 0 <= completed <= count
                and type(calls) is int and calls >= 0):
            lines.append((f'El registro conservado de investigación informa {completed} de {count} análisis acotados completados; '
                          f'invocaciones de modelos: {calls}. El triaje técnico no equivale a investigación completada ni a aprobación humana.'
                          if spanish else
                          f'The retained investigation record reports {completed} of {count} bounded analyses completed; '
                          f'model invocations: {calls}. Technical triage does not equal completed investigation or human approval.'))
        else:
            lines.append('Cobertura de investigación no disponible; el triaje técnico no equivale a investigación completada.' if spanish else
                         'Investigation coverage unavailable; technical triage does not equal completed investigation.')
    if isinstance(register, Mapping) and isinstance(context.get('identity'), Mapping):
        from nico.candidate_investigation_pipeline_v1 import display_investigation
        from nico.candidate_source_reason_detail_v1 import LABELS
        from nico.candidate_investigation_report_scope_v1 import report_identity
        expected_identity = report_identity(context, spanish=spanish)
        view = display_investigation(register, expected_identity) if isinstance(expected_identity, Mapping) else {'available': False}
        reason_labels = {
            'source_parse_unavailable': ('Source parsing unavailable', 'Análisis sintáctico del código no disponible'),
            'source_identity_mismatch': ('Source identity mismatch', 'La identidad del código no coincide'),
            'ambiguous_call_expression': ('Ambiguous call expression', 'Expresión de llamada ambigua'),
            'rule_semantics_require_specialist_review': ('Specialist rule analysis required', 'Se requiere análisis especializado de la regla'),
            'unsupported_or_missing_exact_source_evidence': ('Unsupported or missing exact-source evidence', 'Evidencia del código exacto ausente o no compatible'),
            'rule_source_line_mismatch': ('Rule and source line mismatch', 'La regla no coincide con la línea del código'),
            'source_scope_unavailable_or_stale': ('Source scope unavailable or stale', 'Alcance del código no disponible u obsoleto'),
            'investigation_budget_exhausted': ('Investigation budget exhausted', 'Presupuesto de investigación agotado'),
            'source_file_binding_mismatch': ('Source file binding mismatch', 'La vinculación del archivo no coincide'),
            'source_line_missing': ('Source line unavailable', 'Línea del código no disponible'),
            'retained_observation_invalid': ('Retained observation invalid', 'Observación conservada inválida'),
        }
        if view.get('available'):
            unresolved = view['candidate_count'] - view['completed_count']
            lines.append((f'Candidatos sin resolver: {unresolved}; pendientes de revisión humana.' if spanish else
                          f'Unresolved candidates: {unresolved}; human review pending.'))
            for code, count in sorted(view['unresolved_reasons'].items()):
                labels = reason_labels.get(code, ('Other unresolved evidence or analysis', 'Otra evidencia o análisis sin resolver'))
                lines.append(f'{labels[1 if spanish else 0]}: {count}.')
        elif isinstance(investigation, Mapping):
            lines.append('Desglose de motivos no disponible: identidad o huellas de evidencia no validadas.' if spanish else
                         'Reason breakdown unavailable: identity or evidence fingerprints not validated.')
        if view.get('available') and view.get('source_availability_counts'):
            lines.append('Detalle del subconjunto sin análisis sintáctico disponible:' if spanish else
                         'Breakdown of the subset without available source parsing:')
            lines.append('La ausencia de una observación no demuestra un fallo del analizador ni una causa presupuestaria.' if spanish else
                         'An absent observation proves neither parser failure nor a budget cause.')
            for code, count in view['source_availability_counts'].items():
                lines.append(f'{LABELS[code][1 if spanish else 0]}: {count}.')
    records = context.get('scanner_execution_records')
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, Mapping) or record.get('compact_record') is not True or record.get('raw_findings_embedded') is not False:
            continue
        summary = record.get('finding_summary')
        count = summary.get('raw') if isinstance(summary, Mapping) else None
        display = str(count) if type(count) is int and count >= 0 else ('no disponible' if spanish else 'unavailable')
        name = str(record.get('scanner_name') or record.get('tool') or 'unknown')
        lines.append((f'{name}: recuento de candidatos originales={display}; el recuento original no implica hallazgos materiales confirmados.'
                      if spanish else f'{name}: raw candidate count={display}; raw count does not imply confirmed material findings.'))
    report, identity = context.get('analyzer_evidence_report'), context.get('identity')
    if (isinstance(report, Mapping) and isinstance(identity, Mapping)
            and identity.get('commit_sha') and report.get('commit_sha') == identity.get('commit_sha')):
        lines.extend(stage_preview_labels({'stage_id': 'dependency_security_static_analysis',
                                          '_repeatability_assurance': report}, {}, spanish=spanish))
    return lines
