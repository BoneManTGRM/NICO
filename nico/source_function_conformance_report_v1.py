"""Renderer-neutral tables for the scoped, explicitly excluded conformance ratio."""
from __future__ import annotations

DISPLAY_LIMITATIONS = (
    'Excluded from overall maturity; architecture quality and delivery velocity are not established. '
    'CC<=20 uses enumerated functions in completely acquired eligible Python/JS/TS files; C++ receives no credit. '
    'Languages differ; combined totals are descriptive. Nesting<=4 is separate, with no joint inference. '
    'Helper extraction or trivial-function dilution can increase the ratio without reducing decision burden; never infer improvement from the ratio alone. '
    'Source exclusions, acquisition coverage and enumeration limitations remain in the accompanying measurement/profile tables.'
)


def _ratio(dimension: dict, population: int) -> str:
    percentage = dimension['percentage']
    display = f'{percentage}%' if percentage is not None else 'not applicable' if population == 0 else 'unavailable'
    maximum = dimension['maximum'] if dimension['maximum'] is not None else 'unavailable'
    return (f"{dimension['conforming']} / {dimension['measured_functions']} ({display}); "
            f"Absolute violations: {dimension['violations']}; maximum: {maximum}.")


def conformance_tables(value: dict) -> list[dict]:
    rows = [['Status', value['status']], ['Scope and limitations', DISPLAY_LIMITATIONS]]
    if value['status'] == 'unavailable':
        rows.append(['Qualification', value['reason']])
    else:
        rows.append(['Exact source SHA', value['identity']['snapshot_commit_sha']])
        populations = [('Combined (descriptive)', value['combined']),
                       *((row['language'], row) for row in value['languages'])]
        for label, population in populations:
            cc, nesting = population['cc'], population['nesting']
            rows.append([f'{label} — CC<=20', _ratio(cc, population['function_count']) +
                         f" Sum(CC-1): {cc['sum_cc_minus_1']}; measured files: {population['files']}."])
            rows.append([f'{label} — nesting<=4 (separate)', _ratio(nesting, population['function_count']) +
                         f" Missing functions: {nesting['missing_functions']}."])
    return [{'title': 'Function complexity conformance', 'columns': ['Measure', 'Value'], 'rows': rows}]
