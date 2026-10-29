"""Preserve report identity through display cleanup; never infer it from packets."""
from collections.abc import Mapping
from nico.candidate_investigation_pipeline_v1 import SCOPE_KEYS

KEY = 'candidate_investigation_report_scope'
VERSION = 'nico.candidate-investigation-report-scope.v1'


def report_identity(canonical, *, spanish=False):
    current = canonical.get('identity')
    if spanish and isinstance(current, Mapping):
        # The Spanish rendering projection localizes only this authored missing
        # display label. Restore its canonical label for validation, never a
        # customer/project identifier or evidence-derived scope.
        current = {**current, **{k: 'Not supplied' for k in ('customer_id', 'project_id')
                                if current.get(k) == 'No proporcionado'}}
    if KEY not in canonical:
        # Older producer reports may already retain the same original canonical
        # identity for measurements. Validate that producer context, never an
        # evidence envelope or packet's self-declared scope.
        from nico.retained_section_measurements_v1 import report_measurement_identity
        return report_measurement_identity({**canonical, 'identity': current})
    context = canonical[KEY]
    original = context.get('identity') if isinstance(context, Mapping) else None
    if (not isinstance(context, Mapping) or context.get('artifact_schema') != VERSION
            or not isinstance(original, Mapping) or not isinstance(current, Mapping)
            or not all(isinstance(original.get(k), str) and original[k] for k in SCOPE_KEYS)):
        return None
    from nico.comprehensive_human_review_package_cleanup_v1 import _client_identity
    projected = {k: _client_identity(original[k]) if k in {'customer_id', 'project_id'} else original[k]
                 for k in SCOPE_KEYS}
    if any(projected[k] != current.get(k) for k in SCOPE_KEYS):
        return None
    return {k: original[k] for k in SCOPE_KEYS}
