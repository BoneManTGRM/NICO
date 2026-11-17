from copy import deepcopy
from itertools import product
from nico.scanner_score_lifts import _remove_lines


def test_remove_lines_preserves_normalization_and_filter_semantics():
    cases = [None, False, 0, '', 'keep', 'MISSING proof',
             ['keep', 'missing proof', 3], ('keep', 'missing'),
             {'x': 'value'}, [None, False, {'a': 1}, ['nested']]]
    for findings, unavailable, fragments in product(cases, cases, [(), ('missing',), ('MISSING', 'keep'), ('',)]):
        section = deepcopy({'findings': findings, 'unavailable': unavailable,
                            'other': {'preserved': True}})
        expected = deepcopy(section)
        lowered = tuple(fragment.lower() for fragment in fragments)
        for key in ('findings', 'unavailable'):
            original = expected.get(key) or []
            sequence = original if isinstance(original, list) else [original]
            expected[key] = [item for item in sequence if not any(fragment in str(item).lower() for fragment in lowered)]
        _remove_lines(section, fragments)
        assert section == expected


def test_remove_lines_keeps_missing_and_list_alias_behavior():
    shared = ['keep', 'missing proof']
    section = {'findings': shared, 'other': shared}
    _remove_lines(section, ('missing',))
    assert section == {'findings': ['keep'], 'unavailable': [], 'other': ['keep', 'missing proof']}
    assert section['other'] is shared
    assert section['findings'] is not shared
