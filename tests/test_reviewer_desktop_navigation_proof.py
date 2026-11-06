"""Offline isolation/oracle regressions; actual keyboard execution is hosted-only."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import reviewer_binding_webkit_proof as base
import reviewer_desktop_navigation_proof as desktop
import reviewer_proof_diagnostics as diagnostics


@pytest.mark.parametrize('method,url,expected', [
    ('GET', base.ORIGIN + '/assessment', 'asset'),
    ('GET', base.ORIGIN + '/es/assessment?run_id=comprun_fixture', 'asset'),
    ('GET', base.ORIGIN + '/operations/final-review?lang=es-MX', 'navigation-observation'),
    ('POST', base.ORIGIN + '/assessment', 'blocked'),
    ('POST', base.ORIGIN + '/operations/final-review', 'blocked'),
    ('GET', 'https://app.nicoaudit.com/assessment', 'blocked'),
    ('GET', 'http://127.0.0.1:3107.evil.invalid/assessment', 'blocked'),
    ('GET', base.ORIGIN + '/assessment/extra', 'blocked'),
    ('GET', base.ORIGIN + '/api/nico/assessment/start', 'blocked'),
    ('GET', base.ORIGIN + '/api/nico/assessment/comprehensive-run/real/review-work', 'blocked'),
])
def test_desktop_context_keeps_exact_local_read_only_boundary(method, url, expected):
    assert desktop.request_kind(method, url, base.ORIGIN, base.request_kind) == expected
    if '/assessment' in url or '/operations/final-review' in url:
        assert base.request_kind(method, url) == 'blocked', 'original reviewer policy must remain unchanged'


@pytest.mark.parametrize('locale,case,url', [
    ('en', 'reset', '/operations/final-review'),
    ('es-MX', 'reset', '/operations/final-review?lang=es-MX'),
    ('en', 'invalid', '/operations/final-review'),
    ('en', 'comprehensive-switch', '/operations/final-review?run_id=comprun_new&service=comprehensive&customer_id=newcustomer&project_id=newproject&edition=newedition'),
    ('es-MX', 'express-switch', '/operations/final-review?run_id=express_run_new&service=express&lang=es-MX'),
])
def test_valid_destinations(locale, case, url):
    desktop.validate_destination(base.ORIGIN + url, base.ORIGIN, desktop.expected_scope(locale, case))


@pytest.mark.parametrize('url', [
    '/operations/final-review?run_id=comprun_old',
    '/operations/final-review?customer_id=oldcustomer',
    '/operations/final-review?project_id=oldproject',
    '/operations/final-review?edition=oldedition',
    '/operations/final-review?service=comprehensive',
    '/operations/final-review?run_id=',
    '/operations/final-review#stale',
    '/operations',
])
def test_reset_oracle_rejects_stale_or_wrong_destinations(url):
    with pytest.raises(AssertionError):
        desktop.validate_destination(base.ORIGIN + url, base.ORIGIN, {})


@pytest.mark.parametrize('url', [
    base.ORIGIN + '/operations/final-review?run_id=express_run_new&service=comprehensive&lang=es-MX',
    base.ORIGIN + '/operations/final-review?run_id=express_run_new&service=express',
    base.ORIGIN + '/operations/final-review?run_id=express_run_new&run_id=comprun_old&service=express&lang=es-MX',
    'https://production.invalid/operations/final-review?run_id=express_run_new&service=express&lang=es-MX',
])
def test_switch_oracle_rejects_wrong_service_locale_duplicate_identity_and_origin(url):
    with pytest.raises(AssertionError):
        desktop.validate_destination(url, base.ORIGIN, desktop.expected_scope('es-MX', 'express-switch'))


def test_keyboard_traversal_is_bounded_and_does_not_accept_invisible_focus():
    class Keyboard:
        def __init__(self): self.keys = []
        def press(self, key): self.keys.append(key)
    class Page:
        keyboard = Keyboard()
    class Missing:
        def evaluate(self, expression): return False
    page = Page()
    with pytest.raises(AssertionError, match='not keyboard reachable'):
        desktop.tab_to(page, Missing(), limit=3)
    assert page.keyboard.keys == ['Tab'] * 3
    class Invisible:
        def evaluate(self, expression): return True
        def is_visible(self): return False
    with pytest.raises(AssertionError):
        desktop.tab_to(page, Invisible())


def test_complete_requires_both_full_unique_case_matrices_and_successful_return():
    from copy import deepcopy
    manifest = {'cases': [{'name': f'{locale}-{viewport}-{scenario}', 'status': 'passed'}
                         for locale in ('en', 'es-MX') for viewport in base.VIEWPORTS
                         for scenario in base.SCENARIOS],
                'desktop_navigation_cases': [{'locale': locale, 'case': case, 'status': 'passed'}
                                             for locale in desktop.LOCALES for case in desktop.CASES]}
    assert base.proof_complete(manifest, True)
    assert not base.proof_complete(manifest, False), 'late browser/cleanup failure must not qualify'
    for field in ('cases', 'desktop_navigation_cases'):
        missing = deepcopy(manifest)
        missing[field].pop()
        assert not base.proof_complete(missing, True)
        duplicate = deepcopy(manifest)
        duplicate[field][-1] = duplicate[field][0]
        assert not base.proof_complete(duplicate, True)
        failed = deepcopy(manifest)
        failed[field][-1]['status'] = 'failed'
        assert not base.proof_complete(failed, True)


@pytest.mark.parametrize('name,allowed', [
    ('en-desktop-navigation.png', True), ('es-MX-desktop-navigation.png', True),
    ('en-mobile-navigation.png', False), ('fr-desktop-navigation.png', False),
    ('en-desktop-navigation-extra.png', False),
])
def test_only_two_named_desktop_screenshots_are_staged(tmp_path, name, allowed):
    publish = tmp_path / 'reviewer-binding-webkit-proof' / 'publish'
    publish.mkdir(parents=True)
    (publish / name).write_bytes(b'synthetic-test-image')
    if allowed:
        staged = diagnostics.stage_upload(tmp_path)
        assert (staged / name).read_bytes() == b'synthetic-test-image'
    else:
        with pytest.raises(ValueError, match='unexpected proof artifact'):
            diagnostics.stage_upload(tmp_path)
