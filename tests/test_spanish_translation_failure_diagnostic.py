import json

import pytest

from nico import spanish_translation_failure_diagnostic as diagnostic


def _error(text, field='evidence'):
    return 'missing Spanish presentation translation for ' + field + ': ' + text


def test_real_source_literal_match_is_unique_and_reveals_only_location():
    literal = ('The core decision-report artifacts were generated and retained. '
               'One or more strict package-quality conditions remain review-limited; '
               'later Strategic and final-report gates must still run.')
    result = diagnostic.spanish_translation_failure_diagnostic(_error(literal[:180], 'summary'))
    assert result == {'field': 'summary', 'source_match': 'unique_static_literal',
                      'source_module': 'comprehensive_core_report_readiness_v1', 'source_line': 90}
    assert literal[:50] not in json.dumps(result)


def test_duplicate_authored_literal_is_not_reported_as_unique_origin():
    result = diagnostic.spanish_translation_failure_diagnostic(_error('retained bounded workflow run history'))
    assert result == {'field': 'evidence', 'source_match': 'ambiguous_static_literal'}


def test_ast_excludes_docstrings_and_dynamic_fragments_and_retains_concat():
    source = '''"""private documentation"""
fixed = "owned " "constant"
dynamic = f"Owned authored introduction with enough stable characters: {private} tail"
short = f"Value: {private}"
'''
    locations = list(diagnostic._source_locations(source))
    assert locations == [
        ('dynamic', 'Owned authored introduction with enough stable characters:', 3),
        ('static', 'owned constant', 2),
    ]


def test_dynamic_candidate_never_claims_exact_provenance_or_echoes_values(monkeypatch):
    prefix = 'Owned authored introduction with enough stable characters:'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {}, 'dynamic': {prefix: {('comprehensive_native_providers', 100)}}})
    result = diagnostic.spanish_translation_failure_diagnostic(_error(prefix + ' PRIVATE/path:99'))
    assert result == {'field': 'evidence', 'source_match': 'unique_dynamic_prefix_candidate',
                      'source_module': 'comprehensive_native_providers', 'source_line': 100}
    assert 'PRIVATE' not in json.dumps(result)


def test_dynamic_collision_has_no_location(monkeypatch):
    prefix = 'Owned authored introduction with enough stable characters:'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {}, 'dynamic': {prefix: {('comprehensive_native_providers', 100),
                                         ('comprehensive_report_package', 200)}}})
    result = diagnostic.spanish_translation_failure_diagnostic(_error(prefix + ' PRIVATE'))
    assert result == {'field': 'evidence', 'source_match': 'ambiguous_dynamic_prefix_candidate'}


@pytest.mark.parametrize('error', [None, {}, ['PRIVATE'], 'PRIVATE' * 1000,
    _error('PRIVATE', 'PRIVATE_FIELD'), _error('PRIVATE' * 40),
    'unrecognized Spanish presentation contract: PRIVATE'])
def test_malformed_unknown_and_oversized_errors_are_not_disclosed(error):
    result = diagnostic.spanish_translation_failure_diagnostic(error)
    assert result == {'field': 'other', 'source_match': 'none'}
    assert 'PRIVATE' not in json.dumps(result)


def test_unknown_prose_reports_only_allowlisted_field():
    assert diagnostic.spanish_translation_failure_diagnostic(_error('PRIVATE/path and unknown prose')) == {
        'field': 'evidence', 'source_match': 'none'}


def test_ast_node_budget_is_enforced(monkeypatch):
    monkeypatch.setattr(diagnostic, '_MAX_NODES', 1)
    with pytest.raises(ValueError, match='source_catalog_budget'):
        list(diagnostic._source_locations('value = "literal"'))
