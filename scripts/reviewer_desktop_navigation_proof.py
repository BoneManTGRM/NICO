"""Hosted synthetic keyboard proof; no authentication or screen-reader claim."""
import hashlib
import time
from urllib.parse import parse_qs, urlencode, urlsplit

LOCALES = ('en', 'es-MX')
CASES = {
    'reset': {},
    'invalid': {'run_id': 'invalid'},
    'comprehensive-switch': {'run_id': 'comprun_new', 'customer_id': 'newcustomer',
                             'project_id': 'newproject', 'edition': 'newedition'},
    'express-switch': {'run_id': 'express_run_new'},
}
OLD_SCOPE = {'run_id': 'comprun_old', 'customer_id': 'oldcustomer',
             'project_id': 'oldproject', 'edition': 'oldedition'}
STYLE = """el => {const s=getComputedStyle(el);return JSON.stringify([
 s.outlineStyle,s.outlineWidth,s.outlineColor,s.boxShadow,s.borderColor,s.backgroundColor,s.transform]);}"""


def request_kind(method, url, origin, base_classifier):
    """Only this context adds exact local document routes; API policy is unchanged."""
    parsed = urlsplit(url)
    if method == 'GET' and f'{parsed.scheme}://{parsed.netloc}' == origin:
        if parsed.path in ('/assessment', '/es/assessment'):
            return 'asset'
        if parsed.path == '/operations/final-review':
            return 'navigation-observation'
    return base_classifier(method, url)


def expected_scope(locale, case):
    expected = {'lang': ['es-MX']} if locale == 'es-MX' else {}
    if case in ('comprehensive-switch', 'express-switch'):
        expected.update({k: [v] for k, v in CASES[case].items()})
        expected['service'] = ['comprehensive' if case == 'comprehensive-switch' else 'express']
    return expected


def validate_destination(url, origin, expected):
    parsed = urlsplit(url)
    assert f'{parsed.scheme}://{parsed.netloc}' == origin
    assert parsed.path == '/operations/final-review' and not parsed.fragment
    assert parse_qs(parsed.query, keep_blank_values=True) == expected


def tab_to(page, locator, limit=24, key='Tab'):
    """Reach the control through real keyboard traversal, never programmatic focus."""
    for _ in range(limit):
        page.keyboard.press(key)
        if locator.evaluate('el => el === document.activeElement'):
            assert locator.is_visible()
            assert locator.evaluate("el => el.matches(':focus-visible')")
            return
    raise AssertionError('control not keyboard reachable within bounded traversal')


def run(browser, origin, base_classifier, raw, cases, start, artifact_limit):
    for locale in LOCALES:
        for case, scope in CASES.items():
            assert time.monotonic() - start < 180, 'browser proof budget exhausted'
            context = browser.new_context(viewport={'width': 1280, 'height': 1000},
                                          locale=locale, service_workers='block')
            try:
                context.add_cookies([{'name': 'nico-specialist-session',
                                     'value': 'synthetic-render-only', 'url': origin}])
                requests, errors, destinations = [], [], []

                def route_request(route):
                    req = route.request
                    kind = request_kind(req.method, req.url, origin, base_classifier)
                    requests.append({'method': req.method, 'url': req.url, 'decision': kind})
                    if kind == 'navigation-observation':
                        # Observe native link activation, without loading a review backend.
                        assert req.is_navigation_request() and req.frame == page.main_frame
                        destinations.append(req.url)
                        route.fulfill(status=200, content_type='text/html',
                                      body='<title>Synthetic navigation observation</title>')
                    elif kind == 'asset':
                        route.continue_()
                    elif kind == 'empty':
                        route.fulfill(status=204, body='')
                    else:
                        route.abort('blockedbyclient')

                context.route('**/*', route_request)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.set_default_timeout(5000)
                path = '/es/assessment' if locale == 'es-MX' else '/assessment'
                page.goto(origin + path, wait_until='domcontentloaded', timeout=10000)
                page.locator('main[data-assessment-hydrated="true"]').wait_for()
                page.evaluate('document.fonts.ready')
                nav = page.get_by_role('navigation', name=(
                    'Navegación principal de NICO' if locale == 'es-MX' else 'NICO primary navigation'), exact=True)
                primary = nav.locator('[data-service="run-job"]')
                assert primary.get_attribute('aria-current') == 'page'
                brand = nav.locator('.global-brand')
                language = nav.locator('.language-switcher')
                more = nav.locator('.nav-more > summary')
                final = nav.get_by_role('link', name='Revisión final' if locale == 'es-MX' else 'Final Review', exact=True)

                page.evaluate('(url) => history.replaceState(null, "", url)', path + '?' + urlencode(OLD_SCOPE))
                primary_unfocused = primary.evaluate(STYLE)
                for link in (brand, primary):
                    tab_to(page, link)
                    href = urlsplit(link.get_attribute('href'))
                    assert href.path == path
                    assert parse_qs(href.query)['run_id'] == ['comprun_old']
                page.wait_for_function('(before) => {const el=document.querySelector("[data-service=run-job]");'
                                       'return (' + STYLE + ')(el)!==before;}', arg=primary_unfocused)
                primary_focused = primary.evaluate(STYLE)
                tab_to(page, language)
                alternate = urlsplit(language.get_attribute('href'))
                assert alternate.path == ('/assessment' if locale == 'es-MX' else '/es/assessment')
                assert parse_qs(alternate.query)['run_id'] == ['comprun_old']
                tab_to(page, more)
                page.keyboard.press('Enter')
                assert nav.locator('.nav-more').get_attribute('open') is not None
                tab_to(page, final)
                old_expected = {k: [v] for k, v in OLD_SCOPE.items()}
                old_expected['service'] = ['comprehensive']
                if locale == 'es-MX':
                    old_expected['lang'] = ['es-MX']
                validate_destination(origin + final.get_attribute('href'), origin, old_expected)

                # Native replaceState models the application's reset/switch URL boundary.
                # No link DOM or application handler is replaced by the test.
                query = {**scope, 'new_assessment': 'synthetic'} if case == 'reset' else scope
                page.evaluate('(url) => history.replaceState(null, "", url)', path + '?' + urlencode(query))
                page.keyboard.press('Shift+Tab')
                assert not final.evaluate('el => el === document.activeElement')
                unfocused = final.evaluate(STYLE)
                page.keyboard.press('Tab')
                assert final.evaluate("el => el === document.activeElement && el.matches(':focus-visible')")
                page.wait_for_function('(before) => {const el=document.activeElement;'
                                       'return (' + STYLE + ')(el)!==before;}', arg=unfocused)
                focused = final.evaluate(STYLE)
                expected = expected_scope(locale, case)
                validate_destination(origin + final.get_attribute('href'), origin, expected)
                # Traverse back through the real menu, then verify all primary links
                # also refresh after the same reset/switch boundary.
                tab_to(page, brand, key='Shift+Tab')
                for link, expected_path in ((brand, path), (primary, path), (language,
                        '/assessment' if locale == 'es-MX' else '/es/assessment')):
                    if link != brand:
                        tab_to(page, link)
                    href = urlsplit(link.get_attribute('href'))
                    assert href.path == expected_path
                    observed = parse_qs(href.query, keep_blank_values=True)
                    for field in OLD_SCOPE:
                        assert observed.get(field) == ([scope[field]] if field in scope else None)
                    assert observed.get('new_assessment') == (['synthetic'] if case == 'reset' else None)
                tab_to(page, final)
                validate_destination(origin + final.get_attribute('href'), origin, expected)
                screenshot = None
                if case == 'reset':
                    name = f'{locale}-desktop-navigation.png'
                    pixels = page.screenshot()
                    assert sum(f.stat().st_size for f in raw.iterdir() if f.is_file()) + len(pixels) <= artifact_limit
                    (raw / name).write_bytes(pixels)
                    screenshot = {'name': name, 'sha256': hashlib.sha256(pixels).hexdigest()}
                page.keyboard.press('Enter')
                page.wait_for_url('**/operations/final-review**', wait_until='domcontentloaded')
                assert page.title() == 'Synthetic navigation observation'
                assert len(destinations) == 1
                validate_destination(destinations[0], origin, expected)
                assert not errors, errors
                assert not [r for r in requests if r['method'] != 'GET'], requests
                cases.append({'locale': locale, 'case': case, 'status': 'passed',
                              'native_keys': ['Tab', 'Shift+Tab', 'Enter'],
                              'primary_focus_styles': [primary_unfocused, primary_focused],
                              'final_review_focus_styles': [unfocused, focused],
                              'destination': destinations[0], 'requests': requests,
                              'screenshot': screenshot, 'synthetic_destination_only': True,
                              'screen_reader_observed': False, 'authentication_verified': False})
            finally:
                context.close()
