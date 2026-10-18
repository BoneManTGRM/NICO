"""Full source anchors survive prose extraction and final finding projection."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from nico import client_finding_remediation_register_v1 as producer
from nico import client_finding_remediation_register_v4 as register
from nico import comprehensive_canonical_projection_truth_v55 as projection

SHA = 'e514df5bb5766319c4cd92cd9cc44ad19360f9b9'
REPOSITORY = 'BoneManTGRM/NICO'
ROUTES = [
    ('apps/web/app/api/nico/assessment/[...path]/route.ts', 138, 'proxyAssessment'),
    ('apps/web/app/api/nico/[...path]/route.ts', 160, 'proxyNico'),
]


def prose(path, line=138, symbol='proxyAssessment'):
    return f'Actionable hotspot {path}:{line} · {symbol} · complexity 40.'


@pytest.mark.parametrize('path', [route[0] for route in ROUTES] + [
    'apps/web/[id]/route.ts', 'apps/web/[[...path]]/route.ts',
    'apps/web/[organization]/[project]/route.ts', 'src/plain.ts',
])
def test_producer_retains_entire_path_and_projection_identity(path):
    raw = prose(path)
    matches = list(producer._line_matches(raw, producer._HOTSPOT_LINE, producer._HOTSPOT_LINE_START))
    assert len(matches) == 1
    assert matches[0].group('path') == path
    records = producer._risk_string_records({'evidence': [raw]}, SHA)
    assert len(records) == 1
    assert records[0]['path'] == path
    assert records[0]['location'] == f'{path}:138'
    assert projection._source_path(path) == path.casefold()
    assert projection._source_path(f'{path}:138') == path.casefold()


def canonical_source(routes):
    findings, hotspots, evidence = [], [], []
    for path, line, symbol in routes:
        stable_id = register._stable_id(REPOSITORY, path, line, 'complexity_hotspot', '')
        findings.append({'finding_id': stable_id, 'finding_aliases': [f'explicit-alias-{symbol}-{line}'],
                         'path': path, 'location': f'{path}:{line}', 'line': line, 'symbol': symbol,
                         'title': f'Reduce complexity in {symbol}', 'category': 'architecture',
                         'finding_family': 'complexity_hotspot', 'status': 'open',
                         'fact': 'cyclomatic_complexity=40', 'client_actionable': True})
        hotspots.append({'path': path, 'line': line, 'name': symbol, 'cyclomatic_complexity': 40})
        evidence.append(prose(path, line, symbol))
    return {'identity': {'repository': REPOSITORY, 'commit_sha': SHA},
            'canonical_findings': findings, 'complexity_evidence': {'hotspots': hotspots},
            'architecture': {'findings': evidence}, 'human_review_required': True,
            'client_delivery_allowed': False}


@pytest.mark.parametrize('routes', [ROUTES, [
    ('apps/web/[first]/route.ts', 138, 'sameHandler'),
    ('apps/web/[second]/route.ts', 138, 'sameHandler'),
]])
def test_full_path_records_merge_only_exact_anchors_and_preserve_ids_aliases(routes):
    source = canonical_source(routes)
    before = deepcopy(source)
    built = register.normalize_finding_remediation_register(
        producer.build_finding_remediation_register(source), source)
    findings = projection.canonicalize_final_findings(built['code_findings'])
    assert len(findings) == len(routes)
    by_path = {item['path']: item for item in findings}
    for expected in source['canonical_findings']:
        actual = by_path[expected['path']]
        assert actual['finding_id'] == expected['finding_id']
        assert set(expected['finding_aliases']) <= set(actual['finding_aliases'])
        assert actual['location'] == expected['location']
        assert actual['symbol'] == expected['symbol']
    assert source == before
    assert all(item['path'] != 'route.ts' for item in findings)


def test_projection_keeps_unproven_basename_reference_separate():
    full = canonical_source(ROUTES)['canonical_findings'][0]
    legacy = {**deepcopy(full), 'finding_id': 'unproven-short-id', 'finding_aliases': [],
              'path': 'route.ts', 'location': 'route.ts:138'}
    findings = projection.canonicalize_final_findings([full, legacy])
    assert len(findings) == 2
    assert findings[0]['finding_id'] == full['finding_id']
    assert 'unproven-short-id' not in findings[0]['finding_aliases']
    assert findings[1] == legacy


@pytest.mark.parametrize('length', [1000, 10000, 30000])
def test_bracketed_candidate_scan_does_not_retry_failed_path_suffixes(length):
    prefix = ('a[...path]/' * (length // 11 + 1))[:length]
    raw = prefix + '.ts:invalid · missing · complexity 40\n' + prose(ROUTES[0][0])
    calls = []

    def match(value, position):
        calls.append(position)
        return producer._HOTSPOT_LINE.match(value, position)

    actual = list(producer._line_matches(raw, SimpleNamespace(match=match), producer._HOTSPOT_LINE_START))
    expected = list(producer._HOTSPOT_LINE.finditer(raw))
    assert [(m.span(), m.groupdict()) for m in actual] == [(m.span(), m.groupdict()) for m in expected]
    assert len(calls) < 10
    assert not any(0 < position < length for position in calls)
    assert actual[-1].group('path') == ROUTES[0][0]


@pytest.mark.parametrize('spanish', [False, True])
def test_projected_canonical_and_rendered_register_keep_full_paths(spanish):
    import io
    from pypdf import PdfReader
    source = canonical_source(ROUTES)
    before = deepcopy(source)
    built = register.normalize_finding_remediation_register(
        producer.build_finding_remediation_register(source), source)
    canonical = projection.normalize_final_projection({
        **source, 'canonical_findings': register.canonical_findings_from_register(built)})
    assert len(canonical['canonical_findings']) == 2
    assert canonical['complexity_evidence'] == source['complexity_evidence']
    assert canonical['human_review_required'] is True
    assert canonical['client_delivery_allowed'] is False
    markdown = producer.finding_register_markdown(built, spanish=spanish)
    pdf = producer.render_finding_register_pdf(built, spanish=spanish)
    text = ''.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages)
    compact_text = ''.join(text.split())
    for path, line, _ in ROUTES:
        location = f'{path}:{line}'
        assert location in markdown
        assert location in compact_text
        assert any(item['location'] == location for item in canonical['canonical_findings'])
    assert source == before


@pytest.mark.parametrize('prefix', ['', 'Summary: ', '\n', 'xActionable hotspot '])
def test_bracketed_scan_matches_unoptimized_parser_spans(prefix):
    raw = prefix + prose(ROUTES[0][0]) + '\n' + prose('apps/web/[[...path]]/route.ts', 160, 'proxyNico')
    actual = list(producer._line_matches(raw, producer._HOTSPOT_LINE, producer._HOTSPOT_LINE_START))
    expected = list(producer._HOTSPOT_LINE.finditer(raw))
    assert [(m.span(), m.groupdict()) for m in actual] == [(m.span(), m.groupdict()) for m in expected]
    assert [m.group('path') for m in actual] == [ROUTES[0][0], 'apps/web/[[...path]]/route.ts']


@pytest.mark.parametrize('path', ['src/plain.ts', 'apps/[id]/route.ts',
                                  '[...path]/route.ts', '[[...path]]/route.ts'])
@pytest.mark.parametrize('reference', ['[{path}]', '[{path}:138]',
                                       '[{path}:138](https://example.test/source)',
                                       'Source: `[{path}:138]`'])
def test_projection_wrapped_references_merge_with_exact_path(path, reference):
    wrapped = reference.format(path=path)
    assert projection._source_path(wrapped) == path.casefold()
    common = {'symbol': 'handler', 'finding_family': 'complexity_hotspot'}
    records = [{**common, 'finding_id': 'canonical', 'path': path,
                'recommendation': 'Retain the richer canonical record.'},
               {**common, 'finding_id': 'wrapped', 'exact_source': wrapped}]
    before = deepcopy(records)
    findings = projection.canonicalize_final_findings(records)
    assert len(findings) == 1
    assert findings[0]['finding_id'] == 'canonical'
    assert 'wrapped' in findings[0]['finding_aliases']
    assert records == before


@pytest.mark.parametrize('prefix', ['[', 'a[', 'a/'])
def test_projection_failed_source_token_has_bounded_scan(prefix):
    from time import perf_counter
    raw = prefix * 30000 + 'nonsourcetext'
    started = perf_counter()
    assert projection._SOURCE_RE.search(raw) is None
    elapsed = perf_counter() - started
    # Generous wall-clock guard: a single token must not retry every suffix.
    assert elapsed < 1.0, elapsed
    assert projection._source_path(raw + ' src/plain.ts:138') == 'src/plain.ts'


@pytest.mark.parametrize('value', ['src/plain.ts', 'src/view.tsx', 'a/module.jsx',
                                    'C:/src/plain.py:10', 'file.py prose next.ts',
                                    'text: src/module.yaml', 'src/a.cpp'])
def test_projection_preserves_ordinary_extension_matching(value):
    import re
    legacy = re.compile(
        r'([A-Za-z0-9_.\-/]+\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|java|kt|swift|go|rs|rb|php|cs|c|cc|cpp|h|hpp|sh|yml|yaml|toml|json))',
        re.IGNORECASE)
    assert projection._source_path(value) == legacy.search(value).group(1).casefold()
