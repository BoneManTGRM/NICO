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
        records = retained('review_candidate_register')
        total = str(len(records)) if records is not None else ('desconocido' if spanish else 'unknown')
        rows = [line for line in stage.get('findings') or [] if str(line or '').strip()][:findings_limit]
        return [(
            f'Vista previa del registro de candidatos: {len(rows)} de {total} registros conservados. Registro completo: review_candidate_register en el JSON canónico.'
            if spanish else
            f'Candidate register preview: {len(rows)} of {total} retained records. Complete register: review_candidate_register in canonical JSON.'
        )]
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
