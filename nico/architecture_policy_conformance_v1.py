"""Normative target-source policy, never maturity, quality or delivery authority."""
from copy import deepcopy

from nico.source_function_conformance_v1 import build_conformance

KEY = 'architecture_policy_conformance_v1'
VERSION = 'nico.architecture-policy.function-maintainability.v1'
# Fixed obligations: population growth cannot add passing rules or dilute failures.
RULES = (('function_cc_max_20', 'cc', 20, True),
         ('function_nesting_max_4', 'nesting', 4, False))
LIMIT = ('Only enumerated eligible Python/JS/TS functions. Different parser conventions; '
         'not whole architecture quality, debt cost or delivery velocity. Boundaries, runtime behavior '
         'and semantic duplication are not assessed. Extraction may change this profile without '
         'reducing decision burden. Critical means blocking this policy only, not client approval.')


def build_policy(context, repository, complexity, *, witness=None):
    source = build_conformance(context, repository, complexity, witness=witness)
    qualified = source['status'] in ('qualified', 'not_applicable')
    population = source['combined'] if qualified else None
    rows = []
    for rule_id, dimension, threshold, critical in RULES:
        row = dict(rule_id=rule_id, threshold=threshold, critical=critical,
                   status='unknown', violations=None, observed_violations=None,
                   measured_functions=None, total_functions=None, source_threshold=None,
                   reason='qualified_source_evidence_required')
        if population is not None:
            metric = population[dimension]
            row['measured_functions'] = metric['measured_functions']
            row['total_functions'] = population['function_count']
            row['source_threshold'] = metric['threshold']
            if type(metric['threshold']) is not int or metric['threshold'] != threshold:
                row['reason'] = 'source_policy_threshold_mismatch'
                rows.append(row)
                continue
            row['observed_violations'] = metric['violations']
            if population['function_count'] == 0:
                row.update(status='not_applicable', reason='verified_empty_eligible_function_population')
            elif metric['measured_functions'] == population['function_count']:
                row.update(status='fail' if metric['violations'] else 'pass',
                           violations=metric['violations'], reason='complete_bound_function_population')
            else:
                row['reason'] = 'incomplete_dimension_population'
        rows.append(row)
    counts = {s: sum(r['status'] == s for r in rows)
              for s in ('pass', 'fail', 'unknown', 'not_applicable')}
    denominator = len(RULES) - counts['not_applicable']
    complete = counts['unknown'] == 0
    critical_failures = sum(r['critical'] and r['status'] == 'fail' for r in rows)
    critical_unknown = any(r['critical'] and r['status'] == 'unknown' for r in rows)
    return {
        'version': VERSION, 'status': 'incomplete' if not complete else 'not_applicable' if not denominator else 'fails_policy' if counts['fail'] else 'meets_policy',
        'rules': rows, 'counts': counts, 'rule_inventory_count': len(RULES),
        'normative_denominator': denominator, 'resolved_rule_count': len(RULES)-counts['unknown'],
        'conformance_percentage': round(100*counts['pass']/denominator, 2) if complete and denominator else None,
        'critical_failure_count': critical_failures,
        'critical_status': 'blocked' if critical_failures else 'unknown' if critical_unknown else 'not_applicable' if not denominator else 'clear',
        'identity': deepcopy(source['identity']), 'inventory_sha256': source.get('inventory_sha256'),
        'producer_source_sha256': deepcopy(source.get('producer_source_sha256')),
        'coverage': deepcopy(source['coverage']), 'exclusions': deepcopy(source['exclusions']),
        'function_count': population['function_count'] if population else None,
        'sum_cc_minus_1': population['cc']['sum_cc_minus_1'] if population else None,
        'included_in_overall_maturity': False, 'architecture_quality_established': False,
        'delivery_velocity_established': False, 'changes_acceptance_authority': False,
        'limitations': LIMIT,
    }


COPY_ES = {
    'Architecture policy conformance — function maintainability': 'Conformidad con la política de arquitectura — mantenibilidad de funciones',
    'Architecture policy rules': 'Reglas de la política de arquitectura',
    'Policy version': 'Versión de la política', 'Policy status': 'Estado de la política',
    'Policy pass': 'Cumple', 'Policy fail': 'Incumple', 'Policy unknown': 'Desconocido',
    'Policy not applicable': 'No aplicable', 'Policy incomplete': 'Política incompleta',
    'Policy meets': 'Cumple la política', 'Policy fails': 'Incumple la política',
    'Passed rules': 'Reglas cumplidas', 'Failed rules': 'Reglas incumplidas',
    'Unknown rules': 'Reglas desconocidas', 'Not-applicable rules': 'Reglas no aplicables',
    'Fixed rule inventory': 'Inventario fijo de reglas', 'Resolved rules': 'Reglas resueltas',
    'Applicable rule denominator (unknown included)': 'Denominador de reglas aplicables (incluye desconocidas)',
    'Policy conformance percentage': 'Porcentaje de conformidad con la política',
    'Critical policy failures': 'Incumplimientos críticos de la política',
    'Critical policy status': 'Estado crítico de la política',
    'Policy critical blocked': 'Política bloqueada por incumplimiento crítico',
    'Policy critical clear': 'Sin incumplimientos críticos de la política',
    'Policy critical unknown': 'Estado crítico desconocido',
    'No qualified percentage': 'Sin porcentaje calificado',
    'No functions in verified eligible population': 'Sin funciones en la población elegible verificada',
    'Qualified source evidence required': 'Se requiere evidencia de código fuente calificada',
    'Complete bound function population': 'Población completa de funciones vinculada a la fuente',
    'Incomplete dimension population; observed violations are not exhaustive': 'Población incompleta para esta dimensión; los incumplimientos observados no son exhaustivos',
    'Source and policy thresholds differ': 'Los umbrales de la fuente y de la política difieren',
    'Observed violations': 'Incumplimientos observados',
    'Measured / total functions': 'Funciones medidas / totales',
    'Rule': 'Regla', 'Policy result': 'Resultado de la política',
    'Critical in this policy': 'Crítica en esta política', 'Violations': 'Incumplimientos',
    'Evidence basis': 'Base de evidencia', 'Function CC <=20': 'CC de función <=20',
    'Function nesting <=4': 'Anidamiento de función <=4',
    'Policy scope and limitations': 'Alcance y limitaciones de la política',
    LIMIT: ('Solo funciones elegibles enumeradas de Python/JS/TS. Convenciones de análisis diferentes; '
            'no mide la calidad global de arquitectura, el costo de deuda ni la velocidad de entrega. '
            'No se evalúan límites arquitectónicos, comportamiento en ejecución ni duplicación semántica. '
            'Extraer funciones puede cambiar este perfil sin reducir la carga de decisiones. '
            'Crítico bloquea solo esta política, no autoriza la entrega al cliente.'),
}


def policy_tables(value):
    states = {'pass': 'Policy pass', 'fail': 'Policy fail', 'unknown': 'Policy unknown',
              'not_applicable': 'Policy not applicable', 'incomplete': 'Policy incomplete',
              'meets_policy': 'Policy meets', 'fails_policy': 'Policy fails'}
    reasons = {'verified_empty_eligible_function_population': 'No functions in verified eligible population',
               'qualified_source_evidence_required': 'Qualified source evidence required',
               'complete_bound_function_population': 'Complete bound function population',
               'incomplete_dimension_population': 'Incomplete dimension population; observed violations are not exhaustive',
               'source_policy_threshold_mismatch': 'Source and policy thresholds differ'}
    percentage = value['conformance_percentage']
    return [{'title': 'Architecture policy conformance — function maintainability',
             'columns': ['Measure', 'Value'], 'rows': [
                 ['Policy version', value['version']], ['Policy status', states[value['status']]],
                 ['Fixed rule inventory', value['rule_inventory_count']],
                 ['Passed rules', value['counts']['pass']], ['Failed rules', value['counts']['fail']],
                 ['Unknown rules', value['counts']['unknown']], ['Not-applicable rules', value['counts']['not_applicable']],
                 ['Resolved rules', value['resolved_rule_count']],
                 ['Applicable rule denominator (unknown included)', value['normative_denominator']],
                 ['Policy conformance percentage', f'{percentage}%' if percentage is not None else 'No qualified percentage'],
                 ['Critical policy failures', value['critical_failure_count']],
                 ['Critical policy status', 'Policy not applicable' if value['critical_status']=='not_applicable' else 'Policy critical '+value['critical_status']],
                 ['Policy scope and limitations', LIMIT]]},
            {'title': 'Architecture policy rules',
             'columns': ['Rule', 'Policy result', 'Critical in this policy', 'Observed violations', 'Measured / total functions', 'Evidence basis'],
             'rows': [[('Function CC <=20' if r['rule_id']=='function_cc_max_20' else 'Function nesting <=4'),
                       states[r['status']], r['critical'], r['observed_violations'],
                       (f"{r['measured_functions']} / {r['total_functions']}" if r['total_functions'] is not None else None),
                       reasons[r['reason']]] for r in value['rules']]}]
