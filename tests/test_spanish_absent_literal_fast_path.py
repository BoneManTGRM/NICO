"""Synthetic literal parity and real-renderer coverage; no production acceptance claim."""
import itertools

from nico import comprehensive_spanish_presentation_parity_v1 as parity
from nico import comprehensive_spanish_canonical_report_v87 as canonical


def legacy(text, source, target):
    if not source:
        return text
    pattern = parity._safe_replace_pattern(source)
    return pattern.sub(lambda _match: target, text) if pattern is not None else text.replace(source, target)


def test_absent_literal_does_not_dispatch_regex(monkeypatch):
    def unexpected(_source):
        raise AssertionError('absent literals must not dispatch a regex scan')
    monkeypatch.setattr(parity, '_safe_replace_pattern', unexpected)
    for helper in (parity._safe_replace, canonical._safe_replace):
        assert helper('Retained evidence ' * 750, 'Unrelated phrase', 'replacement') == 'Retained evidence ' * 750


def test_exact_legacy_replacement_semantics():
    sources = ['', 'a', 'Review', 'review', 'human review', 'a.b', 'a+b', '(a)', 'ñ', 'a_b', 'a/b', 'a’b']
    boundaries = ['', ' ', '_', '0', 'A', '.', '/', 'ñ']
    targets = ['', 'APPROVED', r'\1 $ literal', 'á revisión']
    for source, left, right, target in itertools.product(sources, boundaries, boundaries, targets):
        text = left + source + right + ' other ' + source + ' ' + target
        assert parity._safe_replace(text, source, target) == legacy(text, source, target)
    # Preserve ordered substitution when a previous replacement introduces a literal.
    for helper in (parity._safe_replace, legacy):
        text = helper('first', 'first', 'second')
        assert helper(text, 'second', 'tercero') == 'tercero'


def test_actual_localized_pdf_bytes_match_legacy(monkeypatch):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status, _pdf_observation
    from nico.comprehensive_spanish_final_report_runtime_cache_v94 import reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests as reset
    # Offline renderer equivalence; real release admission is tested separately.
    from nico import comprehensive_same_run_locale_report_v1 as locale
    monkeypatch.setattr(locale, 'require_new_report_language', lambda language: None)
    monkeypatch.setattr(locale, 'require_available_projection', lambda status, language: None)
    status = _fixed_status('en')
    reset()
    optimized = _pdf_observation(status, 'es-MX')
    with monkeypatch.context() as patch:
        patch.setattr(parity, '_safe_replace', legacy)
        patch.setattr(canonical, '_safe_replace', legacy)
        reset()
        original = _pdf_observation(status, 'es-MX')
    reset()
    assert optimized == original
