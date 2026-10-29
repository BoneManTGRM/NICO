"""Display retained measurements without deriving scores or delivery performance."""
from collections import Counter
from collections.abc import Mapping
import math
import re
from nico.source_function_measurement_report_v1 import _bound

VERSION = 'nico.retained-section-measurements.v1'
SCOPE_KEYS = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')
LABELS = {
    'files_analyzed': ('Files analyzed for complexity', 'Archivos analizados para complejidad', 'files'),
    'observed_source_files': ('Observed source files', 'Archivos de código observados', 'files'),
    'eligible_source_files': ('Eligible source files', 'Archivos de código elegibles', 'files'),
    'analyzed_source_files': ('Analyzed eligible source files', 'Archivos elegibles analizados', 'files'),
    'import_edges': ('Observed import edges', 'Relaciones de importación observadas', 'edges'),
    'maximum_fan_out': ('Maximum file fan-out', 'Máxima cantidad de dependencias salientes por archivo', 'edges'),
    'duplicate_line_ratio': ('Observed duplicate-line ratio', 'Proporción observada de líneas duplicadas', 'ratio'),
    'duplicate_block_groups': ('Observed duplicate block groups', 'Grupos observados de bloques duplicados', 'groups'),
    'retained_hotspots': ('Retained complexity hotspots — pending review', 'Puntos de complejidad conservados — revisión pendiente', 'entries'),
    'function_count': ('Enumerated functions', 'Funciones enumeradas', 'functions'),
    'cc_maximum': ('Maximum cyclomatic complexity', 'Complejidad ciclomática máxima', 'CC'),
    'nesting_maximum': ('Maximum nesting', 'Anidamiento máximo', 'levels'),
    'cc_measured_functions': ('Functions with measured CC', 'Funciones con complejidad ciclomática medida', 'functions'),
    'cc_missing_functions': ('Functions without measured CC', 'Funciones sin complejidad ciclomática medida', 'functions'),
    'nesting_measured_functions': ('Functions with measured nesting', 'Funciones con anidamiento medido', 'functions'),
    'nesting_missing_functions': ('Functions without measured nesting', 'Funciones sin anidamiento medido', 'functions'),
    'ci_configuration_score': ('CI configuration score — not delivery performance', 'Puntuación de configuración de CI — no es rendimiento de entrega', '/100'),
}
POPULATIONS = frozenset({'analyzed_source', 'retained_preview', 'source_inventory', 'function_observations', 'workflow_configuration'} | {f'{status}:{language}:{method}' for status in ('measured', 'partial') for language, method in (('python', 'python_ast'), ('javascript-typescript', 'typescript_compiler_ast'))})
REASONS = frozenset({'measured_score_missing', 'measured_score_invalid', 'score_input_identity_unproven', 'retained_score_input'})


def score_reason(value):
    """Do not transport arbitrary provider provenance or narrative."""
    reason = value.get('reason') if isinstance(value, Mapping) else None
    return {'reason': reason, 'source_field': 'complexity_evidence.complexity_score'} if isinstance(reason, str) and reason in REASONS else {}


def _number(value, maximum=None):
    return (type(value) in (int, float) and 0 <= value <= 10**15 and math.isfinite(value)
            and (maximum is None or value <= maximum))


def _scope(context, evidence):
    prior = context.get('prior_stage_results')
    snapshot_stage = prior.get('immutable_repository_snapshot') if isinstance(prior, Mapping) else None
    snapshot = snapshot_stage.get('snapshot') if isinstance(snapshot_stage, Mapping) else None
    if not isinstance(evidence, Mapping) or not isinstance(snapshot, Mapping):
        return False
    keys = ('run_id', 'repository', 'customer_id', 'project_id')
    return (all(isinstance(context.get(k), str) and context[k] and evidence.get(k) == context[k]
                and snapshot.get(k) == context[k] for k in keys)
        and evidence.get('snapshot_commit_sha') == context.get('commit_sha') == snapshot.get('commit_sha')
        and isinstance(context.get('commit_sha'), str) and re.fullmatch(r'[0-9a-f]{40}', context['commit_sha']) is not None
        and isinstance(snapshot.get('snapshot_id'), str) and bool(snapshot['snapshot_id'])
        and evidence.get('snapshot_id') == snapshot['snapshot_id']
        and ('commit_sha' not in evidence or evidence['commit_sha'] == context['commit_sha'])
        and isinstance(evidence.get('evidence_id'), str) and bool(evidence['evidence_id']))


def build_section_measurements(context, repository, complexity, sections):
    records = []
    def add(metric, value, population, validation, provenance):
        if value is not None and not _number(value, 1 if metric == 'duplicate_line_ratio' else 100 if metric == 'ci_configuration_score' else None):
            value = None
        if metric != 'duplicate_line_ratio' and value is not None and type(value) is not int:
            value = None
        records.append({'metric': metric, 'value': value, 'unit': LABELS[metric][2],
                        'population': population, 'validation': validation if value is not None else 'unavailable',
                        'commit_sha': context.get('commit_sha'), 'provenance': provenance})
    bound = _scope(context, complexity) and _scope(context, repository)
    provenance = 'complexity_evidence'  # fixed source locator, no provider text
    for field in ('files_analyzed', 'import_edges', 'maximum_fan_out'):
        add(field, complexity.get(field) if bound else None, 'analyzed_source', 'scope_bound', provenance)
    duplicate = complexity.get('duplicate_evidence') if bound else None
    for field in ('duplicate_line_ratio', 'duplicate_block_groups'):
        add(field, duplicate.get(field) if isinstance(duplicate, Mapping) else None, 'analyzed_source', 'scope_bound', provenance)
    hotspots = complexity.get('hotspots') if bound else None
    add('retained_hotspots', len(hotspots) if isinstance(hotspots, list) else None, 'retained_preview', 'pending_review', provenance)
    coverage = complexity.get('profile_coverage') if bound else None
    fields = ('observed_source_files', 'eligible_source_files', 'analyzed_source_files')
    valid_coverage = isinstance(coverage, Mapping) and all(type(coverage.get(k)) is int and coverage[k] >= 0 for k in fields)
    valid_coverage = valid_coverage and coverage['analyzed_source_files'] <= coverage['eligible_source_files'] <= coverage['observed_source_files']
    for field in fields:
        add(field, coverage[field] if valid_coverage else None, 'source_inventory', 'scope_bound', provenance + '.profile_coverage')
    try:
        measurements = _bound(context, repository, complexity) if bound else None
    except (KeyError, TypeError, ValueError, AttributeError):
        measurements = None
    if measurements:
        groups = sorted({(item['status'], item['language'], item['method']) for item in measurements['files'] if item['status'] in {'measured', 'partial'}})
        for status, language, method in groups:
            selected = [item for item in measurements['files'] if (item['status'], item['language'], item['method']) == (status, language, method)]
            population = f'{status}:{language}:{method}'
            function_count = sum(item['metrics']['function_count'] for item in selected)
            add('function_count', function_count, population, status, 'source_function_measurements')
            for dimension, metric in (('cc', 'cc_maximum'), ('nesting', 'nesting_maximum')):
                histogram = Counter()
                for item in selected:
                    histogram.update(item['metrics'][dimension]['histogram'])
                measured_count = sum(histogram.values())
                dimension_status = 'partial' if measured_count < function_count else status
                add(metric, max(map(int, histogram), default=None), population, dimension_status, 'source_function_measurements')
                add(dimension + '_measured_functions', measured_count, population, status, 'source_function_measurements')
                add(dimension + '_missing_functions', function_count - measured_count, population, status, 'source_function_measurements')
    else:
        for metric in ('function_count', 'cc_maximum', 'nesting_maximum'):
            add(metric, None, 'function_observations', 'unavailable', 'source_function_measurements')
    architecture = {'artifact_schema': VERSION, 'identity': {k: context.get(k) for k in SCOPE_KEYS}, 'records': records, 'delivery_performance_measured': False}
    records = []
    workflow = repository.get('workflow_evidence') if isinstance(repository, Mapping) else None
    ci = next((s for s in sections if s.get('id') == 'ci_cd'), {})
    ci_bound = _scope(context, repository) and isinstance(workflow, Mapping) and workflow.get('workflow_configuration_snapshot_sha') == context.get('commit_sha')
    add('ci_configuration_score', ci.get('configuration_maturity_score') if ci_bound else None, 'workflow_configuration', 'scope_bound', 'assessment.sections.ci_cd')
    delivery = {'artifact_schema': VERSION, 'identity': {k: context.get(k) for k in SCOPE_KEYS}, 'records': records, 'delivery_performance_measured': False}
    return {'architecture_debt': architecture, 'velocity_complexity': delivery}


def project_measurements(value, expected_identity=None):
    """Bound the display schema; never accept arbitrary extra provider fields."""
    if not isinstance(value, Mapping) or value.get('artifact_schema') != VERSION or not isinstance(value.get('records'), list):
        return {}
    identity = value.get('identity')
    scope_matches = isinstance(identity, Mapping) and isinstance(expected_identity, Mapping) and all(
        isinstance(expected_identity.get(k), str) and bool(expected_identity[k]) and identity.get(k) == expected_identity[k]
        for k in SCOPE_KEYS)
    records = []
    for row in value['records'][:64]:
        if not isinstance(row, Mapping) or not isinstance(row.get('metric'), str) or row['metric'] not in LABELS:
            continue
        metric = row['metric']; number = row.get('value')
        if number is not None and not _number(number, 1 if metric == 'duplicate_line_ratio' else 100 if metric == 'ci_configuration_score' else None):
            number = None
        if metric != 'duplicate_line_ratio' and number is not None and type(number) is not int:
            number = None
        validation = row.get('validation')
        if not isinstance(validation, str) or validation not in {'scope_bound', 'measured', 'partial', 'pending_review'}:
            number = None
        sha = row.get('commit_sha')
        if not scope_matches or sha != expected_identity.get('commit_sha') or not isinstance(sha, str) or len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
            number = None; sha = None
        population = row.get('population')
        if not isinstance(population, str) or population not in POPULATIONS:
            population = 'unavailable'; number = None
        provenance = row.get('provenance')
        if not isinstance(provenance, str) or provenance not in {'complexity_evidence', 'complexity_evidence.profile_coverage', 'source_function_measurements', 'assessment.sections.ci_cd'}:
            provenance = 'unavailable'; number = None
        records.append({'metric': metric, 'value': number, 'unit': LABELS[metric][2],
            'label_en': LABELS[metric][0], 'label_es': LABELS[metric][1],
            'population': population,
            'validation': validation if number is not None else 'unavailable', 'commit_sha': sha,
            'provenance': provenance})
    return {'artifact_schema': VERSION, 'records': records, 'delivery_performance_measured': False}


def report_tables(assessment, *, spanish=False, expected_identity=None):
    """Reuse the existing technical-analysis stage; no new report or score."""
    tables = []
    for section in assessment.get('sections') or []:
        if not isinstance(section, Mapping) or section.get('id') not in {'architecture_debt', 'velocity_complexity'}:
            continue
        projected = project_measurements(section.get('retained_measurements'), expected_identity)
        if not projected:
            continue
        architecture = section['id'] == 'architecture_debt'
        rows = []
        for record in projected['records']:
            display = (f"{record['value']} {record['unit']}" if record['value'] is not None else 'No disponible' if spanish else 'Unavailable')
            states = {'scope_bound': ('scope-bound', 'vinculada al alcance'), 'measured': ('complete observed population', 'población observada completa'),
                      'partial': ('partial observed population', 'población observada parcial'), 'pending_review': ('pending review; not a confirmed defect', 'revisión pendiente; no es un defecto confirmado'),
                      'unavailable': ('unavailable', 'no disponible')}
            state = states[record['validation']][1 if spanish else 0]
            provenance_labels = {
                'complexity_evidence': ('Bound complexity collector', 'Recopilador de complejidad vinculado'),
                'complexity_evidence.profile_coverage': ('Bound source inventory', 'Inventario de código vinculado'),
                'source_function_measurements': ('Validated function observations', 'Observaciones de funciones validadas'),
                'assessment.sections.ci_cd': ('Exact-source CI configuration assessment', 'Evaluación de configuración de CI del código exacto'),
                'unavailable': ('Unavailable provenance', 'Procedencia no disponible'),
            }
            provenance = provenance_labels[record['provenance']][1 if spanish else 0]
            rows.append([record['label_es' if spanish else 'label_en'], display,
                         f"{record['population']}; {state}; {provenance}; SHA {record['commit_sha'] or '-'}"])

        missing = ('Required calibrated architecture-score input is missing or invalid; code measurements are not a calibrated architecture-quality score.' if architecture else
                   'Delivery performance is not measured: linked events, verified timestamps, observation window and sample size are not established. CI configuration and complexity are not delivery velocity.')
        if spanish:
            missing = ('Falta el dato válido requerido de puntuación calibrada de arquitectura; las mediciones de código no son una puntuación calibrada de calidad arquitectónica.' if architecture else
                       'El rendimiento de entrega no está medido: no se han establecido eventos vinculados, fechas verificadas, período ni tamaño de muestra. La configuración de CI y la complejidad no son velocidad de entrega.')
        if architecture and section.get('score') is not None:
            missing = 'Retained measurements do not change the existing scoring contract.' if not spanish else 'Las mediciones conservadas no cambian el contrato de puntuación existente.'
        rows.append(['Limitaciones' if spanish else 'Limitations', missing, ''])
        tables.append({'measurement_contract': VERSION, 'title': ('Mediciones de arquitectura conservadas' if architecture else 'Configuración de CI y evidencia de entrega') if spanish else
                       ('Retained architecture measurements' if architecture else 'CI configuration and delivery evidence'),
                       'columns': ['Medida', 'Valor y unidad', 'Población, validación y procedencia'] if spanish else ['Measure', 'Value and unit', 'Population, validation and provenance'], 'rows': rows})
    return tables
