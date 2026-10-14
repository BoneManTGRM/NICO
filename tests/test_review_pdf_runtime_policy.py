"""Durable policy identity must not depend on marshal reference bookkeeping."""
import json
import os
import subprocess
import sys

from nico import review_pdf_preparation_api_v1 as api
from nico import retained_pdf_exact_input_cache_v1 as cache


def test_policy_unchanged_when_code_attributes_are_retained(monkeypatch):
    namespace = {}
    exec(compile('def fixture(x):\n return x in {"alpha", "beta", "gamma"}\n', '<policy-fixture>', 'exec'), namespace)
    function = namespace['fixture']
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'e' * 40)
    monkeypatch.setattr(cache, '_live_policy', lambda builder: (function, 64))
    before = api.runtime_policy()
    code = function.__code__
    references = [getattr(code, name) for name in ('co_code', 'co_consts', 'co_names',
        'co_varnames', 'co_freevars', 'co_cellvars', 'co_linetable', 'co_exceptiontable')]
    assert references
    assert api.runtime_policy() == before
    function.__code__ = code.replace(co_consts=tuple(
        frozenset({'changed'}) if isinstance(value, frozenset) else value for value in code.co_consts))
    assert api.runtime_policy() != before
    changed = {}
    exec(compile('def fixture(x):\n return x not in {"alpha", "beta", "gamma"}\n', '<policy-fixture>', 'exec'), changed)
    function.__code__ = changed['fixture'].__code__
    assert api.runtime_policy() != before
    function.__code__ = code
    monkeypatch.setattr(cache, '_live_policy', lambda builder: (function, 65))
    assert api.runtime_policy() != before
    monkeypatch.setattr(cache, '_live_policy', lambda builder: (function, 64))
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'f' * 40)
    assert api.runtime_policy() != before



def test_regex_cache_does_not_change_same_code_policy(monkeypatch):
    import re
    from nico.comprehensive_report_package import _semantic_html
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'e' * 40)
    monkeypatch.setattr(cache, '_live_policy', lambda builder: (_semantic_html,))
    code = _semantic_html.__code__
    re.purge()
    before = api.runtime_policy()
    _semantic_html('', 'synthetic diagnostic')
    assert _semantic_html.__code__ is code
    assert api.runtime_policy() == before
    re.purge()
    assert api.runtime_policy() == before

def test_real_policy_matches_warm_render_and_fresh_process(monkeypatch):
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record, runtime_for
    from nico.storage import PostgresAdapter
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'e' * 40)
    build_owned_record()  # Small synthetic report; no assessment or database.
    runtime_for(PostgresAdapter.__new__(PostgresAdapter))
    warmed = api.runtime_policy()
    script = '''
import json
from scripts.postgres_review_pdf_lifecycle_proof import runtime_for
from nico.storage import PostgresAdapter
from nico.review_pdf_preparation_api_v1 import runtime_policy
runtime_for(PostgresAdapter.__new__(PostgresAdapter))
print(json.dumps(runtime_policy()))
'''
    for seed in ('1', '2'):
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
            env=dict(os.environ, PYTHONHASHSEED=seed), timeout=30)
        assert result.returncode == 0, result.stderr[-1000:]
        assert tuple(json.loads(result.stdout)) == warmed
