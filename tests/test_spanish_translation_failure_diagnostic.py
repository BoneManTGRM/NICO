import json

import pytest

from nico import spanish_translation_failure_diagnostic as diagnostic


def _error(text, field='evidence'):
    return 'missing Spanish presentation translation for ' + field + ': ' + text


def test_real_localization_trace_discloses_only_fixed_context():
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    source = {'stage_id': 'dependency_security_static_analysis',
              'unavailable': ['PRIVATE scanner execution requires missing evidence PRIVATE/path']}
    with pytest.raises(ValueError) as caught:
        _localize_tree([source], path=('stage_summaries',))
    context = diagnostic.translation_exception_context(caught.value)
    assert context == {'container': 'stage_summaries', 'stage': 'dependency_security_static_analysis'}
    assert 'PRIVATE' not in json.dumps(context)
    assert source['unavailable'][0].startswith('PRIVATE')


def test_translation_context_rejects_untrusted_fields_and_other_errors():
    assert diagnostic.sanitize_translation_context({'container': 'PRIVATE', 'stage': 'PRIVATE',
        'text': 'PRIVATE'}) is None
    assert diagnostic.sanitize_translation_context({'container': 'assessment', 'text': 'PRIVATE'}) == {
        'container': 'assessment'}
    assert diagnostic.translation_exception_context(ValueError('PRIVATE')) is None
    assert diagnostic.translation_exception_context(RuntimeError(_error('PRIVATE'))) is None


def test_context_consumer_only_discloses_fixed_values_for_matching_failure():
    from nico.qualification_failure_diagnostics import v2_publication_failure_diagnostic
    value = {'error_type': 'ValueError', 'error': _error('PRIVATE', 'unavailable'),
             'translation_context': {'container': 'assessment', 'stage': 'PRIVATE', 'text': 'PRIVATE'}}
    result = v2_publication_failure_diagnostic(value)
    assert result['translation']['context'] == {'container': 'assessment'}
    assert 'PRIVATE' not in json.dumps(result)
    value['error'] = 'some other error'
    assert 'translation' not in v2_publication_failure_diagnostic(value)


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


def test_ast_excludes_docstrings_and_separates_dynamic_fragments_from_static_concat():
    source = '''"""private documentation"""
fixed = "owned " "constant"
dynamic = f"Owned authored introduction with enough stable characters: {private} tail"
short = f"Value: {private}"
'''
    locations = list(diagnostic._source_locations(source))
    assert locations == [
        ('dynamic', 'Owned authored introduction with enough stable characters:', 3),
        ('fragment', 'Owned authored introduction with enough stable characters:', 3),
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


def test_real_scanner_reason_with_dynamic_leading_name_is_only_a_candidate():
    from nico.comprehensive_authoritative_scanner_truth_v62 import _failure_reason
    # A known tool drives the real producer; only its fixed enum label is emitted.
    reason = _failure_reason('bandit', {'timed_out_tools': ['bandit']})
    result = diagnostic.spanish_translation_failure_diagnostic(_error('bandit: ' + reason, 'unavailable'))
    assert result == {'field': 'unavailable', 'source_match': 'unique_dynamic_fragment_candidate',
                      'source_module': 'comprehensive_authoritative_scanner_truth_v62', 'source_line': 204,
                      'scanner_reason': {'scanner': 'bandit', 'family': 'unclassified',
                                        'snippet_at_limit': False, 'semicolon_present': False}}


def test_noninitial_fragment_does_not_expose_dynamic_values(monkeypatch):
    fragment = 'Owned fixed scanner failure explanation with enough characters.'
    locations = list(diagnostic._source_locations('value = f"{private}: ' + fragment + ' {path}"'))
    assert locations == [('fragment', ': ' + fragment, 1)]
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {}, 'dynamic': {}, 'fragment': {fragment: {('scanner_worker', 100)}}})
    result = diagnostic.spanish_translation_failure_diagnostic(_error('PRIVATE: ' + fragment + ' PRIVATE/path:99'))
    assert result == {'field': 'evidence', 'source_match': 'unique_dynamic_fragment_candidate',
                      'source_module': 'scanner_worker', 'source_line': 100}
    assert 'PRIVATE' not in json.dumps(result) and fragment not in json.dumps(result)


def test_fragment_collision_reports_no_location(monkeypatch):
    fragment = 'Owned fixed scanner failure explanation with enough characters.'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {}, 'dynamic': {}, 'fragment': {fragment: {('scanner_worker', 100),
            ('scanner_evidence_pipeline_v1', 200)}}})
    result = diagnostic.spanish_translation_failure_diagnostic(_error('PRIVATE: ' + fragment))
    assert result == {'field': 'evidence', 'source_match': 'ambiguous_dynamic_fragment_candidate'}


@pytest.mark.parametrize('kind', ['static', 'dynamic'])
def test_fragment_match_never_overrides_existing_match_tier(monkeypatch, kind):
    fragment = 'Owned fixed scanner failure explanation with enough characters.'
    catalog = {'static': {}, 'dynamic': {}, 'fragment': {fragment: {('scanner_worker', 100)}}}
    catalog[kind][fragment] = {('comprehensive_native_providers', 200)}
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: catalog)
    result = diagnostic.spanish_translation_failure_diagnostic(_error(fragment))
    assert result['source_module'] == 'comprehensive_native_providers'
    assert result['source_match'] == ('unique_static_literal' if kind == 'static' else 'unique_dynamic_prefix_candidate')


def test_short_dynamic_fragments_cannot_create_candidates():
    assert list(diagnostic._source_locations('value = f"{private}: short detail {path}"')) == []


@pytest.mark.parametrize('scanner', ['bandit', 'ESLint', 'osv-scanner', 'pip-audit'])
def test_known_scanner_detail_can_match_exact_static_literal_without_echo(monkeypatch, scanner):
    literal = 'Owned source-authored scanner failure.'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {literal: {('scanner_worker', 100)}}, 'dynamic': {}, 'fragment': {}})
    result = diagnostic.spanish_translation_failure_diagnostic(_error(scanner + ': ' + literal, 'unavailable'))
    assert result == {'field': 'unavailable', 'source_match': 'unique_static_literal',
        'source_module': 'scanner_worker', 'source_line': 100, 'source_scope': 'scanner_detail',
        'scanner_reason': {'scanner': scanner.casefold(), 'family': 'unclassified',
                           'snippet_at_limit': False, 'semicolon_present': False}}
    assert literal not in json.dumps(result)


@pytest.mark.parametrize('tool', ['semgrep', 'coverage', 'cppcheck'])
def test_unclassified_scanner_reason_never_echoes_private_text(tool):
    result = diagnostic.spanish_translation_failure_diagnostic(_error(
        tool + ': PRIVATE server/path evidence could not be read; PRIVATE token', 'unavailable'))
    assert result['scanner_reason'] == {'scanner': tool, 'family': 'unclassified',
        'snippet_at_limit': False, 'semicolon_present': True}
    assert 'PRIVATE' not in json.dumps(result)


def test_reason_family_is_a_fixed_predicate_and_unknown_tool_is_not_echoed():
    result = diagnostic.spanish_translation_failure_diagnostic(_error(
        'semgrep: semgrep exceeded its 600-second timeout.', 'unavailable'))
    assert result['scanner_reason']['family'] == 'tool_timeout'
    result = diagnostic.spanish_translation_failure_diagnostic(_error(
        'PRIVATE: semgrep exceeded its 600-second timeout.', 'unavailable'))
    assert 'scanner_reason' not in result
    assert 'PRIVATE' not in json.dumps(result)


def test_private_prefix_does_not_enable_static_substring_lookup(monkeypatch):
    literal = 'Owned source-authored scanner failure.'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {literal: {('scanner_worker', 100)}}, 'dynamic': {}, 'fragment': {}})
    assert diagnostic.spanish_translation_failure_diagnostic(_error('PRIVATE: ' + literal)) == {
        'field': 'evidence', 'source_match': 'none'}
    assert diagnostic.spanish_translation_failure_diagnostic(_error('bandit: PRIVATE ' + literal)) == {
        'field': 'evidence', 'source_match': 'none'}


def test_full_field_and_scanner_detail_static_conflict_has_no_location(monkeypatch):
    literal = 'Owned source-authored scanner failure.'
    monkeypatch.setattr(diagnostic, '_source_catalog', lambda: {
        'static': {literal: {('scanner_worker', 100)},
                   'bandit: ' + literal: {('scanner_evidence_pipeline_v1', 200)}},
        'dynamic': {}, 'fragment': {}})
    assert diagnostic.spanish_translation_failure_diagnostic(_error('bandit: ' + literal)) == {
        'field': 'evidence', 'source_match': 'ambiguous_static_literal'}
