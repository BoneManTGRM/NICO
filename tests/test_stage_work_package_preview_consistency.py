"""Counts and displayed members follow the population bound by the stage producer."""
from copy import deepcopy
import base64
import io
import re

import pytest
from pypdf import PdfReader

from nico.report_preview_labels_v1 import stage_preview_labels
from nico.comprehensive_finding_roadmap_v1 import _roadmap_presentation


def fixture(spanish, stage_id, total):
    packages = [{'package_id': f'NICO-WORK-{i:016X}', 'kind': 'finding_remediation',
                 'title': 'Fixture', 'finding_id': f'NICO-FINDING-{i}',
                 'action': 'Fixture action', 'verification': 'Fixture verification',
                 'suggested_role_type': 'architecture_engineering', 'dependencies': []}
                for i in range(total)]
    presentation = _roadmap_presentation(packages, spanish)
    stage = {'stage_id': stage_id, 'title': 'Fixture stage', 'summary': 'Review required',
             'status': 'review_required', 'findings': [], 'unavailable': []}
    if stage_id == 'risk_reduction_and_executive_briefing':
        stage.update(source_package_ids=[p['package_id'] for p in packages],
                     evidence=presentation['executive'])
    else:
        stage.update(roadmap=packages, evidence=presentation['roadmap'])
    # Use genuine-looking but disjoint IDs so rendered membership checks detect leaks.
    stale = [{'package_id': f'NICO-WORK-{i:016X}'} for i in range(1000, 1006)]
    context = {'_preview_context': {'roadmap': stale}, 'roadmap': stale}
    return packages, stage, context


def members(text):
    return set(re.findall(r'NICO-WORK-[0-9A-F]{16}', text))


@pytest.mark.parametrize('outer_present', [False, True])
@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('stage_id', ['risk_reduction_and_executive_briefing', 'six_month_roadmap'])
@pytest.mark.parametrize('total', [0, 56])
def test_stage_population_survives_stale_or_absent_outer_roadmap(spanish, stage_id, outer_present, total):
    packages, stage, context = fixture(spanish, stage_id, total)
    if not outer_present:
        context = {}
    before = deepcopy((stage, context))
    labels = stage_preview_labels(stage, context, spanish=spanish)
    if stage_id == 'risk_reduction_and_executive_briefing' and not total:
        assert labels == []  # The producer emits no ID preview for an empty population.
    else:
        shown = min(7, total) if stage_id == 'risk_reduction_and_executive_briefing' else total
        assert (f'{shown} de {total}' if spanish else f'{shown} of {total}') in labels[0]
    expected = packages[:7] if stage_id == 'risk_reduction_and_executive_briefing' else packages
    assert members('\n'.join(stage['evidence'])) == {p['package_id'] for p in expected}
    assert (stage, context) == before


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('stage_id', ['risk_reduction_and_executive_briefing', 'six_month_roadmap'])
@pytest.mark.parametrize('total', [0, 56])
def test_rendered_counts_and_members_use_stage_population(spanish, stage_id, total):
    from nico.comprehensive_report_package import _pdf, _markdown, _semantic_html
    packages, stage, context = fixture(spanish, stage_id, total)
    identity = {'repository': 'fixture/repository', 'commit_sha': 'a'*40,
                'run_id': 'fixture-preview', 'project_id': 'fixture', 'tenant_id': 'fixture'}
    before = deepcopy((identity, context, stage))
    # Exercise the shared renderer's Spanish-label path with native Spanish producer copy.
    # This is not a complete Spanish publication/localization qualification.
    localize = (lambda value: value) if spanish else None
    md = _markdown(identity, context, [stage], '2026-10-17T00:00:00Z', localize_presentation=localize)
    html = _semantic_html(md, 'Fixture')
    encoded, error, _ = _pdf(identity, context, [stage], '2026-10-17T00:00:00Z', localize_presentation=localize)
    assert not error
    pdf = ' '.join('\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(base64.b64decode(encoded))).pages).split())
    for rendered, limit in ((md, None), (html, None), (pdf, 100)):
        expected_members = members('\n'.join(stage['evidence'][:limit]))
        assert members(rendered) == expected_members
        labels = stage_preview_labels(stage, context, evidence_limit=limit, evidence_text_limit=1000 if limit else None, spanish=spanish)
        for label in labels:
            assert label in rendered
        assert not (members(rendered) & members(str(context)))
    assert (identity, context, stage) == before
