from copy import deepcopy
import socket
import sqlite3
import sys

import pytest

from nico import candidate_technical_triage_v1 as triage
from nico import candidate_lineage_migration_v1 as lineage
from nico import candidate_lineage_runtime_patch_v1 as runtime
from nico import comprehensive_native_providers_v5 as providers
from tests.test_candidate_call_resolution_v1 import row, capture, SHA, SCOPE

SYNTHETIC = {'s': 'nico.candidate-technical-triage.v1', 'n': 0, 'q': {}, 'x': []}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('external or retained evidence access forbidden')
    monkeypatch.setattr(triage, 'load_default_technical_triage', forbidden)
    monkeypatch.setattr(triage, '_read_encoded_source', forbidden)
    monkeypatch.setattr(lineage, 'load_default_baseline', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    from nico import storage
    for method in ('get', 'put', 'list', 'audit', 'delete', 'query', 'execute'):
        if hasattr(storage.STORE, method):
            monkeypatch.setattr(storage.STORE, method, forbidden)
    for name in ('psycopg', 'psycopg2', 'asyncpg'):
        module = sys.modules.get(name)
        if module:
            for method in ('connect', 'create_pool'):
                if hasattr(module, method):
                    monkeypatch.setattr(module, method, forbidden)
    yield
    assert not calls  # also detects access swallowed by fail-safe exception handlers


@pytest.mark.parametrize('scope', ['unknown', 'test', 'example', 'production'])
@pytest.mark.parametrize('nested', [False, True])
def test_unbound_nonexecutable_claims_require_review(scope, nested):
    claims = {'executable_code': False, 'comment_or_string': True, 'scope': scope}
    candidate = row(**({'deterministic_evidence': claims} if nested else claims))
    candidate['nonexecutable_source_receipt'] = {'verified': True, 'source_sha256': 'a'*64}
    before = deepcopy(candidate)
    result = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=SYNTHETIC)
    finding, = result['findings']
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert finding['review_routing_class'] == 'HUMAN_TECHNICAL_REVIEW'
    assert 'independent_nonexecutable_source_proof' in finding['technical_triage_proof_gaps']
    assert finding['disposition'] == 'review_required'
    assert finding['technical_triage_client_delivery_allowed'] is False
    assert finding['grouped_review_eligible'] is False
    assert candidate == before


@pytest.mark.parametrize('capture_kind', ['absent', 'comment_only', 'wrong_tenant', 'executable'])
def test_missing_or_contradictory_capture_never_proves_exclusion(capture_kind):
    candidate = row(executable_code=False, comment_or_string=True)
    retained = None
    if capture_kind != 'absent':
        source = '# header\n# subprocess.run([])\n' if capture_kind == 'comment_only' else 'import subprocess\nsubprocess.run([])\n'
        retained = capture(source, candidate)
        if capture_kind == 'wrong_tenant': retained['scope']['customer_id'] = 'other'
    finding, = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=SYNTHETIC,
        source_capture=retained, source_scope=SCOPE)['findings']
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert finding['review_routing_class'] == 'HUMAN_TECHNICAL_REVIEW'


def test_legacy_nonexecutable_rationale_cannot_bypass_current_contract():
    candidate = row(executable_code=False, comment_or_string=True,
                    lineage_status='carried_forward_exact', prior_candidate_id='old')
    retained = {'s': SYNTHETIC['s'], 'n': 1,
        'q': {'static_nonexecutable_noise': ['not_actionable', 'high', 'approved_or_nonblocking',
              'retained', 'synthetic rationale', 'synthetic boundary', 'QC', [], 'synthetic rank']},
        'x': [['old', 'static_nonexecutable_noise', None]]}
    result = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=retained)
    assert result['findings'][0]['technical_triage_verdict'] == 'needs_review'
    assert result['technical_triage']['imported_candidate_count'] == 0
    assert result['findings'][0]['disposition'] == 'review_required'


def test_installed_production_builder_does_not_trust_matched_scanner_flags(monkeypatch):
    runtime.install_candidate_lineage_runtime_patch()
    # Supply only synthetic retained inputs while keeping actual lineage/triage logic.
    monkeypatch.setattr(runtime, 'apply_candidate_lineage',
        lambda register: lineage.apply_candidate_lineage(register, baseline={'x': [], 'synthetic': True}))
    monkeypatch.setattr(runtime, 'apply_candidate_technical_triage',
        lambda register, **kwargs: triage.apply_candidate_technical_triage(register, triage=SYNTHETIC, **kwargs))
    scan = {**SCOPE, 'snapshot_commit_sha': SHA, 'scanner_results': [
        {'tool': 'bandit', 'category': 'static', 'findings': [{'rule_id': 'B603', 'path': 'app.py',
          'line': 2, 'severity': 'low', 'message': 'synthetic claim',
          'executable_code': False, 'comment_or_string': True}]}]}
    before = deepcopy(scan)
    result = providers.build_canonical_scanner_finding_register(scan, SHA)
    finding, = result['findings']
    assert finding['deterministic_evidence']['executable_code'] is False
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert finding['review_routing_class'] == 'HUMAN_TECHNICAL_REVIEW'
    assert finding['disposition'] == 'review_required'
    assert result['technical_triage']['human_disposition_created'] is False
    assert result['technical_triage']['quality_control_sample_pool'] == 0
    assert scan == before


def test_separate_b101_harness_rule_remains_proposal_only():
    candidate = row(scope='test'); candidate.update(rule_id='B101', source_path='scripts/synthetic_acceptance_proof.py')
    finding, = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=SYNTHETIC)['findings']
    assert finding['review_routing_class'] == 'QUALITY_CONTROL_ELIGIBLE'
    assert finding['disposition'] == 'review_required'
    assert finding['technical_triage_client_delivery_allowed'] is False


@pytest.mark.parametrize('scope', ['test', 'example'])
def test_scope_alone_does_not_prove_nonexecution(scope):
    candidate = row(executable_code=False, scope=scope)
    candidate['rule_id'] = 'B999'
    finding, = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=SYNTHETIC)['findings']
    assert finding['technical_triage_verdict'] == 'needs_review'
    assert 'independent_nonexecutable_source_proof' in finding['technical_triage_proof_gaps']


def test_other_retained_rationale_is_not_rewritten():
    candidate = row(lineage_status='carried_forward_exact', prior_candidate_id='old')
    retained = {'s': SYNTHETIC['s'], 'n': 1,
        'q': {'synthetic_other_reason': ['not_actionable', 'high', 'approved_or_nonblocking',
              'retained', 'synthetic rationale', 'synthetic boundary', 'QC', [], 'synthetic rank']},
        'x': [['old', 'synthetic_other_reason', None]]}
    result = triage.apply_candidate_technical_triage({'findings': [candidate]}, triage=retained)
    assert result['technical_triage']['imported_candidate_count'] == 1
    assert result['findings'][0]['disposition'] == 'review_required'
    assert result['technical_triage']['human_disposition_created'] is False
