"""Candidate discovery only: parse fixtures; never import or execute their source."""
import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest
from bandit.core.context import Context
from nico_bandit import bounded_candidates as candidates

TLS = 'import requests\n\ndef fetch(url):\n    verify = False\n    return requests.get(url, verify=verify, timeout=5)\n'
MD5 = "import hashlib\n\ndef digest(data):\n    return getattr(hashlib, 'md5')(data).hexdigest()\n"


def discover(source):
    tree = ast.parse(source)
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._bandit_parent = parent
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for plugin in (candidates.nico_requests_bound_false, candidates.nico_hashlib_getattr_md5):
                result = plugin(Context({'node': node}))
                if result:
                    results.append((plugin._test_id, result))
    return results


@pytest.mark.parametrize('source,rule,line', [(TLS, 'B951', 5), (MD5, 'B952', 4),
    (TLS.replace('verify = False', '"docstring"\n    verify = False'), 'B951', 6),
    (MD5.replace('.hexdigest()', ''), 'B952', 4),
    (MD5.replace('(data).hexdigest()', '(data, usedforsecurity=True).digest()'), 'B952', 4)])
def test_supported_candidates(source, rule, line):
    results = discover(source)
    assert len(results) == 1
    assert results[0][0] == rule
    issue = results[0][1]
    assert issue.lineno == line
    assert issue.severity == issue.confidence == 'MEDIUM'
    assert 'review' in issue.text.lower()


@pytest.mark.parametrize('source', [
    TLS.replace('verify = False', 'verify = True'),
    TLS.replace('verify=verify', 'verify=False'),  # native B501 owns direct form
    TLS.replace('verify = False', 'verify = unknown'),
    TLS.replace('verify = False', 'verify = False\n    verify = True'),
    TLS.replace('verify = False', 'verify = True\n    verify = False'),
    TLS.replace('fetch(url)', 'fetch(url, verify)'),
    TLS.replace('fetch(url)', 'fetch(url, requests)'),
    TLS.replace('verify = False', 'if url:\n        verify = False\n    else:\n        verify = True'),
    TLS.replace('verify = False', 'for item in url:\n        verify = False'),
    TLS.replace('verify = False', 'try:\n        verify = False\n    except Exception:\n        verify = True'),
    TLS.replace('requests.get', 'session.get'),
    TLS.replace('requests.get', 'requests.Session().get'),
    TLS.replace('requests.get', "getattr(requests, 'get')"),
    TLS.replace('verify=verify', 'verify=verify, **options'),
    TLS.replace('requests.get(url,', 'requests.get(change(),'),
    TLS.replace('verify = False', 'verify = False\n    log()'),
    TLS.replace('verify = False', 'verify: bool = False'),
    TLS.replace('verify = False', 'global verify\n    verify = False'),
    TLS.replace('verify = False', 'nonlocal verify\n    verify = False'),
    TLS.replace('verify = False', 'verify = False\n    del verify'),
    TLS.replace('import requests', 'import unrelated as requests'),
    TLS.replace('import requests', 'from requests import get'),
    TLS.replace('import requests', 'import requests\nrequests = unrelated'),
    TLS.replace('import requests', 'import requests\nimport unrelated as requests'),
    TLS.replace('def fetch', '@decorate\ndef fetch'),
    TLS.replace('fetch(url)', 'fetch(url=side_effect())'),
    TLS.replace('fetch(url)', 'fetch(url: side_effect())'),
    TLS.replace('fetch(url)', 'fetch(url, *, requests=None)'),
    TLS.replace('fetch(url)', 'fetch(url, *requests)'),
    TLS.replace('fetch(url)', 'fetch(url, **requests)'),
    'class Scope:\n' + ''.join('    '+line+'\n' for line in TLS.splitlines()),
    'def outer():\n' + ''.join('    '+line+'\n' for line in TLS.splitlines()),
    TLS + '\nrequests.get = unrelated\n',
    TLS + '\ndef mutate():\n    requests.get = unrelated\n',
    TLS + '\ndef mutate():\n    setattr(requests, "get", unrelated)\n',
    TLS + '\ndef mutate():\n    alias = requests\n    alias.get = unrelated\n',
    TLS + '\ndef mutate():\n    requests.__dict__["get"] = unrelated\n',
    TLS + '\ndef mutate():\n    del requests.__dict__["get"]\n',
    MD5.replace("'md5'", "'sha256'"),
    MD5.replace("'md5'", "algorithm"),
    MD5.replace("'md5'", "'m' + 'd5'"),
    MD5.replace("'md5'", "'MD5'"),
    MD5.replace("getattr(hashlib, 'md5')", 'hashlib.md5'),  # native B324 owns direct
    MD5.replace('digest(data)', 'digest(data, getattr)'),
    MD5.replace('digest(data)', 'digest(data, hashlib)'),
    MD5.replace('import hashlib', 'import unrelated as hashlib'),
    MD5.replace('import hashlib', 'import hashlib\nimport unrelated as getattr'),
    MD5.replace('return getattr', 'getattr = other\n    return getattr'),
    MD5.replace("getattr(hashlib, 'md5')", "getattr(other, 'md5')"),
    MD5.replace("getattr(hashlib, 'md5')", "getattr(hashlib, 'md5', fallback)"),
    MD5.replace('(data).hexdigest()', '(data, usedforsecurity=False).hexdigest()'),
    MD5.replace('(data).hexdigest()', '(data, usedforsecurity=unknown).hexdigest()'),
    MD5.replace('(data).hexdigest()', '(data, **options).hexdigest()'),
    MD5.replace('(data).hexdigest()', '(change()).hexdigest()'),
    MD5.replace('return getattr', 'if data:\n        return getattr'),
])
def test_clean_and_unsupported_forms_not_promoted(source):
    assert discover(source) == []


def test_independent_scopes_and_ast_cache():
    source = TLS + '\ndef safe(url):\n    verify = True\n    return requests.get(url, verify=verify, timeout=5)\n'
    results = discover(source)
    assert len(results) == 1 and results[0][0] == 'B951'


def test_resource_limit_is_explicit_and_bounded(monkeypatch, caplog):
    monkeypatch.setattr(candidates, 'MAX_NODES', 3)
    assert discover(TLS) == []
    assert 'AST resource limit' in caplog.text


def test_parent_depth_limit(monkeypatch, caplog):
    monkeypatch.setattr(candidates, 'MAX_DEPTH', 1)
    assert discover(TLS) == []
    assert 'parent depth limit' in caplog.text


def test_no_application_package_import_on_plugin_load():
    code = 'import sys; import nico_bandit.bounded_candidates; assert "nico" not in sys.modules'
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_registered_plugins_and_native_output(tmp_path):
    # Same native CLI as ordinary scanner; built-in rules remain enabled.
    (tmp_path / 'app.py').write_text(TLS + MD5.replace('import hashlib\n', '')
                                   + '\ndef direct(url):\n    return requests.get(url, verify=False, timeout=5)\n')
    source = (tmp_path / 'app.py').read_text()
    (tmp_path / 'app.py').write_text('import hashlib\n' + source)
    result = subprocess.run([sys.executable, '-I', '-m', 'bandit', '-r', '.', '-f', 'json'],
                            cwd=tmp_path, capture_output=True)
    assert result.returncode == 1, result.stderr.decode()
    payload = json.loads(result.stdout)
    assert payload['errors'] == []
    assert sorted(r['test_id'] for r in payload['results']) == ['B501', 'B951', 'B952']
    assert 'not universally' in next(r['issue_text'] for r in payload['results'] if r['test_id'] == 'B952')


def test_malformed_source_retains_native_error(tmp_path):
    (tmp_path / 'app.py').write_text('def broken(:\n')
    result = subprocess.run([sys.executable, '-I', '-m', 'bandit', '-r', '.', '-f', 'json'],
                            cwd=tmp_path, capture_output=True)
    payload = json.loads(result.stdout)
    assert payload['errors'] and payload['results'] == []


def test_candidates_remain_human_review_under_existing_classifier():
    from nico.bandit_triage import classify_bandit_finding
    for source in (TLS, MD5):
        rule, issue = discover(source)[0]
        record = classify_bandit_finding(dict(test_id=rule, issue_severity=issue.severity,
            issue_confidence=issue.confidence, issue_text=issue.text, filename='app.py', line_number=issue.lineno))
        assert record['classification'] == 'needs_human_review'
        assert record['human_review_required'] is True
        assert record['approved'] is False


def test_large_width_is_bounded(monkeypatch):
    tree = ast.Module(body=[ast.Pass()] * 1000, type_ignores=[])
    monkeypatch.setattr(candidates, 'MAX_NODES', 10)
    assert candidates._nodes(tree) is None


@pytest.mark.parametrize('case', json.loads((Path(__file__).parent / 'fixtures/bounded_python_candidates/cases.json').read_text())['cases'], ids=lambda case: case['id'])
@pytest.mark.parametrize('member', ['clean', 'defect'])
def test_original_independent_pairs_in_installed_native_scanner(tmp_path, case, member):
    source = case['clean_source']
    if member == 'defect':
        assert source.count(case['before']) == 1
        source = source.replace(case['before'], case['after'])
    (tmp_path / 'app.py').write_text(source)
    result = subprocess.run([sys.executable, '-I', '-m', 'bandit', '-r', '.', '-f', 'json'],
                            cwd=tmp_path, capture_output=True)
    assert result.returncode in (0, 1), result.stderr.decode()
    payload = json.loads(result.stdout)
    assert payload['errors'] == []
    rules = {'tls-literal': 'B501', 'tls-variable': 'B951', 'hash-direct': 'B324', 'hash-getattr': 'B952'}
    expected = [] if member == 'clean' else [(rules[case['id']], case['line'])]
    assert [(r['test_id'], r['line_number']) for r in payload['results']] == expected
