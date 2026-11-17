from copy import deepcopy

from nico.complexity_artifact_integration import _clear_stale_complexity_lines
from nico.complexity_score_integrity_patch import _remove_stale_complexity_lines
from nico import evidence_ledger


CASES = [None, False, 0, '', 'retained', ('retained',), {'retained': True},
         ['retained', None, False, 4, {'nested': True}]]


def test_complexity_line_normalization_preserves_types_filtering_and_aliases():
    configurations = [
        (_clear_stale_complexity_lines, ('evidence', 'findings', 'unavailable'),
         ['COMPLEXITY ENGINE stale', 'CURRENT-RUN COMPLEXITY stale',
          'DEEPER COMPLEXITY ANALYSIS stale', 'MISSING RUNTIME ARTIFACTS stale',
          'SOURCE-FOOTPRINT stale', 'RELEASE-READINESS LIFT NOT APPLIED stale',
          'COMPLEXITY PROOF IS INCOMPLETE stale']),
        (_remove_stale_complexity_lines,
         ('evidence', 'findings', 'unavailable', 'verified_claims', 'unverified_claims'),
         ['COMPLEXITY EVIDENCE UNAVAILABLE FOR SCORING stale',
          'SAME-RUN ANALYZER DID NOT PRODUCE VALID MEASUREMENTS stale',
          'MAINTAINABILITY AND COMPLEXITY CONCLUSIONS REMAIN UNAVAILABLE stale',
          'COMPLEXITY-DEPENDENT ARCHITECTURE AND TECHNICAL-DEBT CONCLUSIONS ARE NOT VERIFIED stale',
          'INVALID_OR_ZERO_COMPLEXITY_EVIDENCE stale']),
    ]
    for cleaner, keys, stale in configurations:
        for value in CASES:
            section = {'score': 23, 'status': 'gray', **{key: deepcopy(value) for key in keys}}
            expected = deepcopy(section)
            for key in keys:
                original = expected[key] or []
                expected[key] = original if isinstance(original, list) else [original]
            cleaner(section)
            assert section == expected
            cleaner(section)
            assert section == expected
        for line in stale:
            original = ['retained', line]
            section = {key: original for key in keys}
            section['unrelated'] = original
            cleaner(section)
            assert all(section[key] == ['retained'] for key in keys)
            assert section['unrelated'] is original
            assert original == ['retained', line]
        missing = {'score': 23}
        cleaner(missing)
        assert missing == {'score': 23, **{key: [] for key in keys}}


def test_ledger_section_normalization_preserves_order_context_and_input(monkeypatch):
    calls = []
    def capture(**kwargs):
        calls.append(kwargs)
        return None if kwargs['line'] == 'skip' else kwargs
    monkeypatch.setattr(evidence_ledger, '_entry_from_line', capture)
    for value in CASES + [['first', 'skip', 'last']]:
        section = {'id': 'static_analysis', **{key: deepcopy(value) for key in ('evidence', 'findings', 'unavailable')}}
        result = {'generated_at': 'fixed-time', 'repository': 'owner/repo', 'commit_sha': 'revision',
                  'sections': [None, 'ignored', section]}
        before = deepcopy(result)
        calls.clear()
        actual = evidence_ledger._section_entries(result, 'report-run')
        values = value or []
        normalized = values if isinstance(values, list) else [values]
        expected = [dict(report_run_id='report-run', section=section, line=str(line), source=source,
                         generated_at='fixed-time', repository='owner/repo', commit_sha='revision')
                    for source in ('evidence', 'findings', 'unavailable') for line in normalized]
        assert calls == expected
        assert actual == [entry for entry in expected if entry['line'] != 'skip']
        assert result == before
    assert evidence_ledger._section_entries({'sections': None}, 'report-run') == []
