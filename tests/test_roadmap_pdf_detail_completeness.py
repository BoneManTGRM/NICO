"""Full installed rendering of provisional roadmap details, without private data."""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import subprocess
import sys
from copy import deepcopy

import pytest
from pypdf import PdfReader



def _five_gap_package(language, finding_count=0):
    from tests.test_v2_premium_report_renderer import _package
    from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap
    from nico import phase3_evidence_core_v1 as core
    from nico.phase3_planning_synthesis_v1 import historical_trends_provider

    package = _package(language)
    canonical = package['json']
    canonical['canonical_findings'] = [
        {**deepcopy(canonical['canonical_findings'][0]), 'finding_id': f'RISK-P2-{index:03d}',
         'priority': 'P2', 'location': f'apps/web/app/page{index}.tsx:100'}
        for index in range(finding_count)
    ]
    canonical['stage_summaries'] = [
        {'stage_id': stage_id, 'status': 'complete', 'summary': 'Stage evidence was recorded.',
         'evidence': [], 'findings': [], 'unavailable': []}
        for stage_id in ('six_month_roadmap', 'staffing_sequencing_and_cost',
                         'risk_reduction_and_executive_briefing')
    ]
    context = {**canonical['identity'], 'prior_stage_results': {}}
    providers = (core.functional_qa_provider, core.platform_parity_provider,
                 core.stakeholder_alignment_provider, core.requirements_traceability_provider,
                 historical_trends_provider)
    raw_stages = {provider.__name__: provider(context) for provider in providers}
    if finding_count:
        # Bind to the reconciled finding records, as the production producer does.
        from nico.phase17_canonical_artifact_rebuild_v1 import _prepare_client_artifact_package
        canonical = _prepare_client_artifact_package({'json': canonical})['json']
    package['json'] = bind_final_finding_roadmap(canonical, raw_stages=raw_stages)
    assert len(package['json']['roadmap']) == 5 + finding_count
    return package


def _normalized(text):
    return ' '.join(text.split())


def _assert_five_package_details(language):
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    _install_production_wrappers()
    package = _five_gap_package(language)
    before = deepcopy(package)
    source_stage = next(stage for stage in package['json']['stage_summaries']
                        if stage['stage_id'] == 'six_month_roadmap')
    expected_lines = source_stage['evidence']
    # Action, required input, rationale, verification, and role/dependencies for
    # each package. Merely finding five IDs in the executive summary is inadequate.
    assert len(expected_lines) == 25
    rendered = rebuild_client_artifacts(package)
    pages = [page.extract_text() or '' for page in
             PdfReader(io.BytesIO(base64.b64decode(rendered['pdf_base64']))).pages]
    text = _normalized('\n'.join(pages))
    for line in expected_lines:
        assert _normalized(line) in text, line
    last_id = package['json']['roadmap'][-1]['package_id']
    last_lines = [line for line in expected_lines if line.startswith(last_id + ' | ')]
    assert len(last_lines) == 5
    for line in last_lines:
        assert _normalized(line) in text
    # Require retained detailed sections, not just the bounded summary preview.
    heading = ('Hoja de ruta de seis meses — Evidencia conservada' if language == 'es-MX'
               else 'Six-Month Roadmap — Retained Evidence')
    detailed_pages = [page for page in pages if heading in page]
    assert len(detailed_pages) >= 2
    detailed_text = _normalized('\n'.join(detailed_pages))
    for line in expected_lines:
        assert _normalized(line) in detailed_text, line
    assert package == before
    assert rendered['json']['roadmap'] == before['json']['roadmap']
    assert rendered['json']['client_delivery_allowed'] is False
    assert rendered['json']['human_review_required'] is True


def _assert_dense_package_details(language):
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    _install_production_wrappers()
    package = _five_gap_package(language, finding_count=10)
    before = deepcopy(package)
    rendered = rebuild_client_artifacts(package)
    canonical = rendered['json']
    assert len(canonical['canonical_findings']) == 10
    assert len(canonical['roadmap']) == 15
    stage = next(stage for stage in canonical['stage_summaries']
                 if stage['stage_id'] == 'six_month_roadmap')
    expected = stage['evidence']
    assert len(expected) >= 75
    pages = [page.extract_text() or '' for page in
             PdfReader(io.BytesIO(base64.b64decode(rendered['pdf_base64']))).pages]
    heading = ('Hoja de ruta de seis meses — Evidencia conservada' if language == 'es-MX'
               else 'Six-Month Roadmap — Retained Evidence')
    detailed_pages = [page for page in pages if heading in page]
    assert len(detailed_pages) >= 3
    detailed = _normalized('\n'.join(detailed_pages))
    for line in expected:
        assert _normalized(line) in detailed, line
    assert package == before
    assert canonical['client_delivery_allowed'] is False
    assert canonical['human_review_required'] is True


def _check_in_fresh_process(helper, language, temporary_root):
    # Production installers mutate module bindings. Neither collection nor test
    # execution may install them in the shared unit-test process.
    root = Path(__file__).resolve().parents[1]
    from tests.owned_worker_environment import owned_worker_environment
    environment = owned_worker_environment(root, temporary_root, os.environ)
    code = ("import runpy,sys; "
            "module=runpy.run_path(sys.argv[1]); "
            "module[sys.argv[2]](sys.argv[3]); "
            "print('ROADMAP_DETAIL_CHECK_OK')")
    completed = subprocess.run(
        [sys.executable, '-c', code, str(Path(__file__).resolve()), helper, language],
        cwd=root, env=environment, text=True, capture_output=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert 'ROADMAP_DETAIL_CHECK_OK' in completed.stdout


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_pdf_retains_every_five_package_detail_across_continuation(language, tmp_path):
    _check_in_fresh_process('_assert_five_package_details', language, tmp_path)


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_dense_nonzero_finding_roadmap_retains_every_detail(language, tmp_path):
    _check_in_fresh_process('_assert_dense_package_details', language, tmp_path)
