"""Bounded synthetic fixtures for the production decision-restoration chain."""
from copy import deepcopy
import io
import re
from time import perf_counter

import pytest
from nico import comprehensive_decision_content_restoration_v66 as restoration
from nico.comprehensive_decision_content_restoration_v67 import restore_decision_content
from nico.comprehensive_canonical_projection_truth_v55 import normalize_final_projection
from nico.comprehensive_report_content_render_v66 import _rich_detailed_findings
from nico.comprehensive_client_ready_projection_v1 import (
    compact_finding_register_markdown, render_compact_finding_register_pdf,
)

PATHS = ['apps/web/app/api/nico/assessment/[...path]/route.ts',
         'apps/web/app/api/nico/[...path]/route.ts',
         '[id]/route.ts', '[[...path]]/route.ts', 'src/plain.ts']


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('wrapper', ['{path}', '[{path}:138]', '[{path}](source)', '`[{path}:138]`'])
def test_restoration_exact_path_and_wrappers(path, wrapper):
    for key in ('path', 'source_path', 'file', 'filename', 'location'):
        assert restoration._path_from_hotspot({key: wrapper.format(path=path)}) == path


@pytest.mark.parametrize('prefix', ['[', 'a[', 'a/'])
def test_restoration_failed_token_scan_is_bounded(prefix):
    raw = prefix * 30000 + 'nonsourcetext'
    start = perf_counter()
    assert restoration._PATH_RE.search(raw) is None
    assert perf_counter() - start < 1.0
    assert restoration._path_from_hotspot({'location': raw, 'file': 'src/plain.ts'}) == 'src/plain.ts'


@pytest.mark.parametrize('path', ['src/plain.py', 'src/view.tsx', 'src/view.jsx',
                                  'src/a.yaml', 'src/a.json', 'src/module.ts'])
def test_restoration_ordinary_extension_behavior_unchanged(path):
    legacy = re.compile(r'([A-Za-z0-9_.\-/]+\.(?:py|tsx?|jsx?|mjs|cjs|json|ya?ml|toml))')
    assert restoration._path_from_hotspot({'path': path}) == legacy.search(path).group(1)


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('structured', [False, True])
def test_restored_architecture_canonical_and_render_chain(spanish, structured):
    from pypdf import PdfReader
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    from nico.comprehensive_spanish_presentation_parity_v1 import install_comprehensive_spanish_presentation_parity_v1
    install_spanish_publication_preflight_v93()
    install_comprehensive_spanish_presentation_parity_v1()
    hotspots = [{'path': path, 'line': 138, 'name': 'sameHandler',
                 'cyclomatic_complexity': 40} for path in PATHS]
    stages = {'ci_cd_architecture_complexity_velocity': {'complexity_evidence': {'hotspots': hotspots}}}
    findings = restoration._synthesized_complexity_findings(hotspots, 'a' * 40)
    for index, item in enumerate(findings):
        item['finding_aliases'] = [f'retained-alias-{index}']
    assessment = {'findings_register': findings} if structured else {}
    source = {'human_review_required': True, 'client_delivery_allowed': False, 'score': 93}
    before = deepcopy((source, stages, assessment))
    canonical, restored, manifest = restore_decision_content(
        source, raw_stages=stages, assessment=assessment, commit_sha='a' * 40)
    assert (source, stages, assessment) == before
    assert {item['path'] for item in canonical['architecture_hotspots']} == set(PATHS)
    assert {item['path'] for item in restored['architecture_hotspots']} == set(PATHS)
    assert manifest['complexity_finding_count_synthesized'] == (0 if structured else len(PATHS))
    canonical = normalize_final_projection(canonical)
    actual = canonical['canonical_findings']
    assert len(actual) == len(PATHS)
    assert {item['finding_id'] for item in actual} == {item['finding_id'] for item in findings}
    if structured:
        assert {alias for item in actual for alias in item['finding_aliases']} >= {
            f'retained-alias-{i}' for i in range(len(PATHS))}
    assert canonical['score'] == 93
    assert canonical['human_review_required'] is True
    assert canonical['client_delivery_allowed'] is False
    assert manifest['human_review_required'] is True
    assert manifest['client_delivery_allowed'] is False
    register = {'code_findings': actual}
    markdown = compact_finding_register_markdown(register, spanish=spanish)
    detailed = _rich_detailed_findings(actual, spanish=spanish)
    pdf = render_compact_finding_register_pdf(register, spanish=spanish)
    text = ''.join(''.join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf)).pages)
    for path in PATHS:
        assert f'{path}:138' in markdown
        assert f'{path}:138' in detailed
        assert f'{path}:138' in text


@pytest.mark.parametrize('path', PATHS)
def test_spanish_acceptance_preserves_complete_machine_location(path):
    from nico.comprehensive_spanish_exit_criteria_v88 import _translate_generated_complexity_contract
    source = f'The exact-SHA rerun no longer reports cyclomatic complexity of 30 or greater at {path}:138.'
    translated = _translate_generated_complexity_contract(source)
    assert translated is not None
    assert f'{path}:138' in translated
    assert '30' in translated
    for invalid in ('Unsupported: ' + source, source + ' Approval granted.', source.replace(':138', ':unknown')):
        assert _translate_generated_complexity_contract(invalid) is None
