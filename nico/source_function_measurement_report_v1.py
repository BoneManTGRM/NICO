"""Report-only projection of independently bound, optional function observations."""
from __future__ import annotations

from collections import Counter
from typing import Any

from nico.full_assessment_complexity_evidence import _is_source_path
from nico.source_architecture_evidence_v1 import verified_observation
from nico.source_function_measurements_v1 import KEY, validate_measurements

UNAVAILABLE = "Function measurements unavailable: absent, invalid, or not independently bound to this engagement, snapshot and source inventory."
LIMITS = (
    "NOT SCORED. Observations concern enumerated functions in supplied source text only, not overall architecture qualification. "
    "Complete means a file's enumerated population, not complete repository coverage. Partial parser observations are reported separately. "
    "Whole-source decision burden and module/class initializer residuals are unavailable; Python lambdas are not enumerated. "
    "Languages use different counting rules. Extraction can lower maximum CC without reducing sum(CC-1); neither is a calibrated quality score. "
    "Absolute counts include observations beyond the retained top-50 hotspot locations; no additional locations are inferred. "
    "Existing scored-subset interpretation, weights, disabled complexity score and dependent velocity proxy are unchanged."
)


def _bound(context: dict, repository: dict, complexity: dict) -> dict | None:
    observation = verified_observation(repository, context)
    if observation is None:
        return None
    snapshot = context['prior_stage_results']['immutable_repository_snapshot']['snapshot']
    identity = {key: context.get(key) for key in ('run_id', 'repository', 'customer_id', 'project_id')}
    if any(not isinstance(value, str) or not value for value in identity.values()):
        return None
    if any(envelope.get(key) != value for envelope in (repository, complexity, snapshot)
           for key, value in identity.items()):
        return None
    identity.update(snapshot_id=snapshot.get('snapshot_id'), snapshot_commit_sha=context.get('commit_sha'))
    if any(envelope.get(key) != value for envelope in (repository, complexity)
           for key, value in identity.items()):
        return None
    # Independent observed text inventory includes all profiled text. Apply only
    # the existing path policy. Content-based exclusions cannot be reconstructed
    # from hashes: a different membership must remain unavailable, not guessed.
    inventory = [{'path': row['path'], 'source_text_sha256': row['observed_text_sha256']}
                 for row in observation['input_inventory'] if _is_source_path(row['path'])]
    inventory.sort(key=lambda row: row['path'])
    value = complexity.get(KEY)
    try:
        return value if validate_measurements(value, expected_identity=identity, expected_inventory=inventory) else None
    except ValueError:
        return None


def measurement_tables(context: dict, repository: dict, complexity: dict) -> list[dict[str, Any]]:
    value = _bound(context, repository, complexity)
    def table(title, rows):
        return {'title': title, 'columns': ['Measure', 'Value'], 'rows': rows}
    if value is None:
        return [table('Function measurement availability', [['Status', UNAVAILABLE]])]
    files = value['files']
    counts = Counter(row['status'] for row in files)
    tables = [table('Function measurement scope', [
        ['Status', 'Bound source observations; NOT SCORED'],
        ['Supplied eligible source files', len(files)],
        ['Complete observed files', counts['measured']], ['Partial observed files', counts['partial']],
        ['Missing files', counts['missing']], ['Unsupported files', counts['unsupported']],
        ['Limitations', LIMITS],
    ])]
    # Keep language/method and parser completeness populations distinct; never
    # use the attachment's aggregate, which includes partial observations.
    groups = sorted({(row['status'], row['language'], row['method']) for row in files
                     if row['status'] in {'measured', 'partial'}})
    for status, language, method in groups:
        selected = [row for row in files if (row['status'], row['language'], row['method']) == (status, language, method)]
        population = sum(row['metrics']['function_count'] for row in selected)
        rows = [['Files', len(selected)], ['Enumerated functions', population]]
        for dimension in ('cc', 'nesting', 'loc'):
            histogram = Counter()
            for row in selected:
                histogram.update(row['metrics'][dimension]['histogram'])
            measured = sum(histogram.values())
            rows.extend([[f'{dimension.upper()} measured functions', measured],
                         [f'{dimension.upper()} missing functions', population - measured],
                         [f'{dimension.upper()} maximum', max(map(int, histogram), default=None)]])
            if dimension == 'cc':
                rows.append(['Sum(CC-1) in enumerated functions', sum((int(k)-1)*n for k,n in histogram.items())])
                # Exact bins retain the distribution without inventing a new
                # threshold or assigning quality labels.
                rows.extend([[f'CC {k}: functions', histogram[k]] for k in sorted(histogram, key=int)])
            thresholds = {'cc': (11, 21), 'nesting': (5,), 'loc': (80,)}[dimension]
            rows.extend([[f'{dimension.upper()} at least {threshold}: functions',
                          sum(n for k,n in histogram.items() if int(k) >= threshold)] for threshold in thresholds])
        label = 'Complete observed population' if status == 'measured' else 'Partial observed population (parser incomplete)'
        tables.append(table(f'{label}: {language} / {method}', rows))
    return tables
