"""Add qualified conformance to existing observations without repeating metrics."""
from __future__ import annotations

from copy import deepcopy

# These supplement the existing observation limitations, which remain visible.
CONFORMANCE_LIMITATIONS = (
    'Delivery velocity is not established. Qualification requires completely acquired eligible Python/JS/TS files; unsupported C++ receives no credit. '
    'Combined totals are descriptive. CC<=20 and nesting<=4 are separate marginals, with no joint inference. '
    'Trivial-function dilution can increase the ratio without reducing decision burden; never infer improvement from the ratio alone.'
)


def _ratio(dimension: dict, population: int) -> str:
    percentage = dimension['percentage']
    display = f'{percentage}%' if percentage is not None else 'not applicable' if population == 0 else 'unavailable'
    return f"{dimension['conforming']} / {dimension['measured_functions']} ({display})"


def _ratios(population: dict) -> list[list]:
    return [['Function complexity conformance — CC<=20', _ratio(population['cc'], population['function_count'])],
            ['Nesting<=4 conformance (separate marginal)', _ratio(population['nesting'], population['function_count'])]]


def _combined_summary(population: dict) -> dict:
    cc, nesting = population['cc'], population['nesting']
    return {'title': 'Function complexity conformance — combined descriptive totals',
            'columns': ['Measure', 'Value'], 'rows': [
                ['Files', population['files']], ['Enumerated functions', population['function_count']],
                *_ratios(population), ['CC>20 absolute violations', cc['violations']],
                ['CC maximum', cc['maximum']], ['Sum(CC-1) in enumerated functions', cc['sum_cc_minus_1']],
                ['NESTING measured functions', nesting['measured_functions']],
                ['NESTING missing functions', nesting['missing_functions']],
                ['Nesting>4 absolute violations', nesting['violations']], ['NESTING maximum', nesting['maximum']],
            ]}


def _compact_identical_counts(rows: list[list]) -> list[list]:
    result = deepcopy(rows)
    for labels, title in (
        (('Supplied eligible source files', 'Complete observed files'),
         'Supplied eligible source / complete observed files'),
        (('Partial observed files', 'Missing files', 'Unsupported files'),
         'Partial observed / missing / unsupported files'),
        (('Enumerated functions', 'CC measured functions', 'NESTING measured functions', 'LOC measured functions'),
         'Functions (enumerated; measured: CC, NESTING, LOC)'),
        (('CC missing functions', 'NESTING missing functions', 'LOC missing functions'),
         'Missing functions (CC, NESTING, LOC)'),
    ):
        selected = [row for row in result if row[0] in labels]
        if len(selected) == len(labels) and all(row[1] == selected[0][1] for row in selected):
            first = result.index(selected[0])
            result = [row for row in result if row[0] not in labels]
            result.insert(first, [title, selected[0][1]])
    return result


def integrate_conformance(tables: list[dict], value: dict) -> list[dict]:
    """Keep every original observation row and distribution; append only new facts."""
    result = deepcopy(tables)
    scope = result[0]
    status = next(row for row in scope['rows'] if row[0] == 'Status')
    status[1] += f"; function complexity conformance: {value['status']}"
    scope['rows'] = _compact_identical_counts(scope['rows'])
    limitations = next((row for row in scope['rows'] if row[0] == 'Limitations'), None)
    if limitations is None:
        scope['rows'].append(['Conformance limitations', CONFORMANCE_LIMITATIONS])
    else:
        limitations[1] += ' ' + CONFORMANCE_LIMITATIONS
    if value['status'] == 'unavailable':
        scope['rows'].append(['Conformance qualification', value['reason']])
        return result
    scope['rows'].append(['Exact source SHA', value['identity']['snapshot_commit_sha']])
    for population in value['languages']:
        title = f"Complete observed population: {population['language']} / "
        summary = next(table for table in result if table['title'].startswith(title))
        summary['rows'] = _compact_identical_counts(summary['rows'])
        summary['rows'].extend(_ratios(population))
    if len(value['languages']) == 1:
        summary['rows'].append(['Combined descriptive totals',
                             f"Identical to the {value['languages'][0]['language']} complete population above; values shown once."])
    else:
        result.append(_combined_summary(value['combined']))
    return result
