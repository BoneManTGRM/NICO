from copy import deepcopy
import hashlib

import pytest

from nico.candidate_call_resolution_v1 import candidate_call_fact
from nico.candidate_source_observations_v1 import observe_python_source
from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage
from nico.candidate_workspace_capture_v1 import capture_candidates
from tests.test_candidate_workspace_capture_v1 import memory

SHA = 'a' * 40
SCOPE = dict(run_id='run', repository='example/repo', commit_sha=SHA,
             customer_id='customer', project_id='project')


def row(line=2, **changes):
    return dict(candidate_id='candidate', finding_id='finding', scanner='bandit',
                category='static', evidence_quality='exact_source', severity='low',
                rule_id='B603', source_path='app.py', line=line,
                exact_commit_sha=SHA, source_commit_sha=SHA,
                disposition='review_required', **changes)


def capture(source, candidate):
    inventory, read, _ = memory({'app.py': source.encode()})
    return capture_candidates([candidate], SCOPE, inventory, read)


@pytest.mark.parametrize('rule', ['B603', 'B607'])
@pytest.mark.parametrize('source,line,api', [
    ('import subprocess\nsubprocess.run(["tool"])\n', 2, 'subprocess.run'),
    ('import subprocess as sp\nsp.Popen(["tool"])\n', 2, 'subprocess.Popen'),
    ('from subprocess import check_call as invoke\ninvoke(["tool"])\n', 2, 'subprocess.check_call'),
    ('from subprocess import check_output\ndef f():\n    check_output(["tool"])\n', 3, 'subprocess.check_output'),
    ('import subprocess as sp\ndef f():\n    sp.call(["tool"])\n', 3, 'subprocess.call'),
])
def test_exact_blob_alias_resolution_supplies_syntax_not_safety(source, line, api, rule):
    candidate = row(line)
    candidate['rule_id'] = rule
    retained = capture(source, candidate)
    original = deepcopy((candidate, retained))
    result = apply_candidate_technical_triage({'findings': [candidate]},
        source_capture=retained, source_scope=SCOPE)
    finding = result['findings'][0]
    fact = finding['technical_triage_call_resolution']
    assert fact['attempted'] is True and fact['status'] == 'resolved'
    assert fact['api'] == api and fact['scope'] == SCOPE and fact['line'] == line
    assert fact['source_sha256'] == hashlib.sha256(source.encode()).hexdigest()
    assert 'executable_source_confirmation' not in finding['technical_triage_proof_gaps']
    assert {'first_party_reachability', 'existing_mitigation_assessment', 'realistic_exploitability',
            'supported_security_boundary'} <= set(finding['technical_triage_proof_gaps'])
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert finding['disposition'] == 'review_required'
    assert finding['candidate_id'] == candidate['candidate_id']
    assert finding['source_commit_sha'] == SHA
    assert finding['technical_triage_client_delivery_allowed'] is False
    assert result['technical_triage']['human_disposition_created'] is False
    assert f'static_import_binding={api}' in finding['evidence_used']
    assert (candidate, retained) == original


@pytest.mark.parametrize('source,line', [
    ('import subprocess as sp\nsp = other\nsp.run([])\n', 3),
    ('import subprocess as sp\ndef f(sp):\n    sp.run([])\n', 3),
    ('import subprocess as sp\nsp.run = other\nsp.run([])\n', 3),
    ('import subprocess as sp\ndel sp\nsp.run([])\n', 3),
    ('import subprocess as sp\nfor sp in items:\n    sp.run([])\n', 3),
    ('import subprocess as sp\ntry:\n    pass\nexcept Exception as sp:\n    sp.run([])\n', 5),
    ('import subprocess as sp\nmatch item:\n    case sp:\n        sp.run([])\n', 4),
    ('import subprocess as sp\nimport other as sp\nsp.run([])\n', 3),
    ('if enabled:\n    import subprocess as sp\nsp.run([])\n', 3),
    ('sp.run([])\nimport subprocess as sp\n', 1),
    ('import subprocess as sp\ngetattr(sp, name)([])\n', 2),
    ('import subprocess as sp\nsp.run(build())\n', 2),
    ('import subprocess as sp\nfrom other import *\nsp.run([])\n', 3),
    ('import subprocess as sp\nexec(code)\nsp.run([])\n', 3),
    ('import subprocess as sp\nglobals()[name] = other\nsp.run([])\n', 3),
    ('import subprocess as sp\nsetattr(sp, name, other)\nsp.run([])\n', 3),
    ('import subprocess as sp\nsp.__dict__["run"] = other\nsp.run([])\n', 3),
    ('import subprocess as sp\nother = sp\nother.run = lambda x: None\nsp.run([])\n', 4),
    ('import subprocess as sp\nf = exec\nf("sp=other")\nsp.run([])\n', 4),
    ('import subprocess as sp\nmutate(sp)\nsp.run([])\n', 3),
    ('import subprocess as sp\nregistry = [sp]\nregistry[0].run = other\nsp.run([])\n', 4),
    ('from subprocess import run\nalias = run\nalias.__code__ = other\nrun([])\n', 4),
    ('import subprocess as sp\nf = globals\nf()["sp"] = other\nsp.run([])\n', 4),
    ('import subprocess as sp\nimport builtins as b\nf = b.exec\nf("sp=other")\nsp.run([])\n', 5),
    ('import subprocess as sp\nf = __builtins__["exec"]\nf("sp=other")\nsp.run([])\n', 4),
    ('import subprocess as sp\nfrom builtins import exec as f\nf("sp=other")\nsp.run([])\n', 4),
    ('import subprocess as sp\nimport subprocess as other\nother.run = replacement\nsp.run([])\n', 4),
    ('from subprocess import run\nimport subprocess as other\nother.run = replacement\nrun([])\n', 4),
    ('import subprocess as sp\nimport sys\nsys.modules["subprocess"].run = other\nsp.run([])\n', 4),
    ('import subprocess as sp\ndef mutate():\n    import subprocess as other\n    other.run = replacement\nmutate()\nsp.run([])\n', 6),
    ('import subprocess as sp\nfrom subprocess import __dict__ as data\ndata["run"] = other\nsp.run([])\n', 4),
    ('import subprocess as sp\nfrom sys import modules as mods\nmods["subprocess"].run = other\nsp.run([])\n', 4),
    ('import subprocess as sp\nfrom builtins import getattr as g\nf = g(obj, "exec")\nf(code)\nsp.run([])\n', 5),
    ('import subprocess as sp\n[sp.run([]) for sp in items]\n', 2),
    ('from .subprocess import run\nrun([])\n', 2),
    ('import subprocess as sp\nsp.unknown([])\n', 2),
    ('import subprocess as sp\nsp.run([]); sp.call([])\n', 2),
    ('from subprocess import run\ndef run(x): pass\nrun([])\n', 3),
])
def test_ambiguous_dynamic_or_shadowed_calls_remain_unresolved(source, line):
    candidate = row(line)
    result = apply_candidate_technical_triage({'findings': [candidate]},
        source_capture=capture(source, candidate), source_scope=SCOPE)
    finding = result['findings'][0]
    assert finding['technical_triage_call_resolution']['status'] == 'unresolved'
    assert 'executable_source_confirmation' in finding['technical_triage_proof_gaps']
    assert finding['technical_triage_verdict'] == 'needs_review'


@pytest.mark.parametrize('field,value', [('run_id', 'other'), ('repository', 'other/repo'),
    ('customer_id', 'other'), ('project_id', 'other'), ('commit_sha', 'b' * 40)])
def test_capture_scope_mismatch_never_contributes_facts(field, value):
    candidate = row()
    retained = capture('import subprocess\nsubprocess.run([])\n', candidate)
    retained['scope'][field] = value
    assert candidate_call_fact(candidate, retained, SCOPE)['status'] == 'unresolved'


@pytest.mark.parametrize('field,value', [('line', 1), ('line', 99), ('exact_commit_sha', 'b' * 40),
    ('source_commit_sha', 'b' * 40), ('source_repository', 'other/repo'), ('source_path', 'other.py'),
    ('candidate_evidence_context_status', 'ambiguous')])
def test_candidate_binding_mismatch_never_contributes_facts(field, value):
    candidate = row()
    retained = capture('import subprocess\nsubprocess.run([])\n', candidate)
    candidate[field] = value
    assert candidate_call_fact(candidate, retained, SCOPE)['status'] == 'unresolved'


@pytest.mark.parametrize('field,value', [('complete_source_blob', False), ('call_resolution_version', 'old'),
    ('parse_warning_count', 1), ('source_sha256', 'bad'), ('statements', None), ('calls', None)])
def test_old_partial_or_malformed_observations_cannot_supply_proof(field, value):
    candidate = row()
    retained = capture('import subprocess\nsubprocess.run([])\n', candidate)
    retained['observations']['app.py'][field] = value
    assert candidate_call_fact(candidate, retained, SCOPE)['status'] == 'unresolved'


def test_truncated_source_wrong_blob_and_parse_failure_do_not_resolve():
    source = b'import subprocess\nsubprocess.run([])\nsubprocess = other\n'
    oid = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    truncated = observe_python_source(source.split(b'subprocess =')[0], repository=SCOPE['repository'],
        commit_sha=SHA, path='app.py', blob_oid=oid)
    assert truncated['status'] == 'source_binding_invalid'
    retained = capture('import subprocess\nsubprocess.run(\n', row())
    assert candidate_call_fact(row(), retained, SCOPE)['status'] == 'unresolved'


def test_conflicting_nonexecutable_context_cannot_clear_or_confirm():
    candidate = row(executable_code=False, comment_or_string=True)
    retained = capture('import subprocess\nsubprocess.run([])\n', candidate)
    finding = apply_candidate_technical_triage({'findings': [candidate]},
        source_capture=retained, source_scope=SCOPE)['findings'][0]
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert 'conflicting_executable_source_evidence' in finding['technical_triage_proof_gaps']


def test_forged_candidate_receipt_and_missing_capture_cannot_supply_facts():
    candidate = row(technical_triage_call_resolution={'status': 'resolved', 'api': 'subprocess.run'})
    finding = apply_candidate_technical_triage({'findings': [candidate]})['findings'][0]
    assert finding['technical_triage_call_resolution']['status'] == 'unresolved'
    assert 'executable_source_confirmation' in finding['technical_triage_proof_gaps']


def test_resolution_accounting_distinguishes_attempts_from_missing_capture_and_disposition():
    rows = [row(), dict(row(), candidate_id='dynamic', line=3),
            dict(row(), candidate_id='missing', source_path='missing.py'),
            dict(row(), candidate_id='unsupported', rule_id='B105')]
    retained = capture('import subprocess\nsubprocess.run([])\nunknown([])\n', rows[0])
    result = apply_candidate_technical_triage({'findings': rows}, source_capture=retained, source_scope=SCOPE)
    metrics = result['technical_triage']['source_call_resolution']
    assert {k: metrics[k] for k in ('eligible', 'attempted', 'resolved', 'unresolved', 'not_attempted')} == {
        'eligible': 3, 'attempted': 2, 'resolved': 1, 'unresolved': 2, 'not_attempted': 1}
    assert len(result['findings']) == 4
    assert all(r['disposition'] == 'review_required' for r in result['findings'])


def test_source_receipts_do_not_expose_aliases_arguments_or_credentials():
    source = 'import subprocess as PRIVATE_ALIAS\nPRIVATE_ALIAS.run(["PRIVATE_COMMAND", "PRIVATE_TOKEN"])\n'
    retained = capture(source, row())
    fact = candidate_call_fact(row(), retained, SCOPE)
    assert fact['status'] == 'resolved'
    assert all(value not in str((retained, fact)) for value in ('PRIVATE_ALIAS', 'PRIVATE_COMMAND', 'PRIVATE_TOKEN'))


def test_decoded_text_legacy_capture_cannot_claim_verified_blob_binding():
    from nico.candidate_investigation_pipeline_v1 import capture_sources
    retained = capture_sources({'app.py': 'import subprocess\nsubprocess.run([])\n'}, SCOPE)
    assert candidate_call_fact(row(), retained, SCOPE)['reason'] == 'complete_parser_proof_unavailable'


def test_installed_scanner_builder_consumes_current_capture_before_triage():
    import subprocess
    import sys
    script = '''
from copy import deepcopy
from tests.test_candidate_call_resolution_v1 import row, capture, SHA, SCOPE
from nico.candidate_lineage_runtime_patch_v1 import install_candidate_lineage_runtime_patch
from nico import comprehensive_native_providers_v5 as providers
install_candidate_lineage_runtime_patch()
retained = capture('import subprocess as sp\\nsp.run([])\\n', row())
scan = {**SCOPE, 'snapshot_commit_sha': SHA, 'candidate_source_capture_attempted': True,
    'candidate_source_observations': retained,
    'scanner_results': [{'tool': 'bandit', 'category': 'static', 'findings': [
        {'rule_id': 'B603', 'path': 'app.py', 'line': 2, 'severity': 'low', 'message': 'subprocess candidate'}]}]}
before = deepcopy(scan)
result = providers.build_canonical_scanner_finding_register(scan, SHA)
finding, = result['findings']
assert finding['technical_triage_call_resolution']['status'] == 'resolved'
assert 'executable_source_confirmation' not in finding['technical_triage_proof_gaps']
assert finding['technical_triage_verdict'] == 'needs_review'
assert finding['disposition'] == 'review_required'
assert result['technical_triage']['human_disposition_created'] is False
assert scan == before
scan['snapshot_commit_sha'] = 'b' * 40
stale = providers.build_canonical_scanner_finding_register(scan, SHA)['findings'][0]
assert stale['technical_triage_call_resolution']['status'] == 'unresolved'
assert 'executable_source_confirmation' in stale['technical_triage_proof_gaps']
'''
    completed = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_import_heavy_input_does_not_scan_module_body_for_each_import():
    import ast
    from nico.candidate_call_resolution_v1 import resolve_calls
    from nico.candidate_workspace_capture_v1 import FILE_LIMIT

    source = ''.join(f'import math as m{i}\n' for i in range(4096))
    source += 'import subprocess as sp\nsp.run([])\n'
    assert len(source.encode()) < FILE_LIMIT
    tree = ast.parse(source)

    class NoLinearMembership(list):
        def __contains__(self, value):
            raise AssertionError('per-import linear module-body membership scan')

    tree.body = NoLinearMembership(tree.body)
    bindings = resolve_calls(tree)
    assert list(bindings.values()) == [{'status': 'resolved', 'reason': 'unshadowed_module_import',
                                       'api': 'subprocess.run', 'import_line': 4097}]
