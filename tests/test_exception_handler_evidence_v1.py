"""Synthetic source fixtures only; optional syntax facts never resolve findings."""
import ast
from copy import deepcopy
import hashlib
import json
import os
import subprocess

import pytest

from nico import exception_handler_evidence_v1 as facts
from nico import candidate_workspace_capture_v1 as collector
from nico.candidate_investigation_pipeline_v1 import (
    capture_sources, display_investigation, fingerprint, investigate_register,
)
from nico.candidate_investigation_finalization_v1 import final_investigation_scope, finalize_investigation
from tests.test_candidate_investigation_pipeline_v1 import SCOPE
from tests.test_candidate_workspace_capture_v1 import memory

PASS = b'try:\n    work()\nexcept Exception:\n    pass\n'
CONTINUE = b'for item in items:\n    try:\n        work()\n    except Exception:\n        continue\n'


def row(**changes):
    return dict(candidate_id='synthetic-candidate', scanner='bandit', category='static',
                evidence_quality='exact_source', exact_commit_sha=SCOPE['commit_sha'],
                source_path='example.py', line=3, rule_id='B110', disposition='review_required',
                **changes)


def capture(rows=None, source=PASS, *, clock=lambda: 0):
    rows = [row()] if rows is None else rows
    inventory, read, _ = memory({'example.py': source})
    return collector.capture_candidates(rows, SCOPE, inventory, read, clock=clock)


def packet(rows=None, source=PASS):
    rows = [row()] if rows is None else rows
    retained = capture(rows, source)
    register = {'findings': rows}
    register['candidate_investigation'] = investigate_register(register, retained, SCOPE, clock=lambda: 0)
    return register, retained


@pytest.mark.parametrize('source,rule,line,kind', [
    (PASS, 'B110', 3, 'single_pass'), (CONTINUE, 'B112', 4, 'single_continue'),
])
def test_capture_persistence_and_projection_never_claim_resolution(source, rule, line, kind):
    candidate = row(); candidate.update(rule_id=rule, line=line)
    register, retained = packet([candidate], source)
    before = deepcopy((register, retained))
    receipt = register['candidate_investigation']['packets'][0]['exception_handler']
    assert receipt['body_kind'] == kind and receipt['line'] == line
    assert receipt['source_sha256'] == hashlib.sha256(source).hexdigest()
    assert receipt['candidate_input_sha256'] == fingerprint(candidate)
    view = display_investigation(register, SCOPE, trusted_capture=retained)
    assert view['packets'][0]['exception_handler'] == receipt
    assert view['packets'][0]['source_sha256'] == receipt['source_sha256']
    assert view['completed_count'] == 0 and view['packets'][0]['completed'] is False
    assert view['unresolved_reasons'] == {'rule_semantics_require_specialist_review': 1}
    assert register['findings'][0]['disposition'] == 'review_required'
    assert register['candidate_investigation']['human_review_required'] is True
    assert register['candidate_investigation']['client_delivery_allowed'] is False
    assert (register, retained) == before


@pytest.mark.parametrize('source,rule,line', [
    (b'try:\n    work()\nexcept Exception:\n    log()\n    pass\n', 'B110', 3),
    (b'try:\n    work()\nexcept Exception:\n    pass\n    raise\n', 'B110', 3),
    (b'try:\n    work()\nexcept Exception: pass; pass\n', 'B110', 3),
    (b'try:\n    work()\nexcept Exception:\n    if flag: pass\n', 'B110', 3),
    (PASS, 'B112', 3), (CONTINUE, 'B110', 4), (PASS, 'B110', 4),
    (b'try:\n    work()\nexcept Exception:\n    continue\n', 'B112', 3),
    (b'for item in items:\n    pass\nelse:\n    try: work()\n    except Exception: continue\n', 'B112', 5),
    (b'try:\n    work()\nexcept* Exception:\n    pass\n', 'B110', 3),
    (b'# except Exception: pass\n', 'B110', 1), (b'try (', 'B110', 1),
])
def test_unsupported_or_mismatched_structure_abstains(source, rule, line):
    candidate = row(); candidate.update(rule_id=rule, line=line)
    register, retained = packet([candidate], source)
    assert 'exception_handler' not in register['candidate_investigation']['packets'][0]
    assert display_investigation(register, SCOPE, trusted_capture=retained)['completed_count'] == 0


@pytest.mark.parametrize('field,value', [
    ('source_path', 'other.py'), ('exact_commit_sha', 'b' * 40),
    ('source_commit_sha', 'b' * 40), ('source_repository', 'other/repo'),
    ('run_id', 'other'), ('customer_id', 'other'), ('project_id', 'other'),
    ('line', True), ('line', 0), ('line', '3'), ('rule_id', 'B101'),
    ('scanner', 'unknown'), ('evidence_quality', 'count_only'),
    ('candidate_evidence_context_status', 'ambiguous'),
])
def test_wrong_candidate_cannot_borrow_fact(field, value):
    retained = capture()
    candidate = row(); candidate[field] = value
    assert facts.qualify(candidate, retained, SCOPE) is None


@pytest.mark.parametrize('damage', [
    'legacy', 'wrong_scope', 'wrong_hash', 'wrong_oid', 'wrong_line', 'wrong_kind',
    'extra_text', 'malformed_map', 'oversized', 'multiple_paths', 'legacy_decoded', 'warning', 'incomplete',
])
def test_trusted_capture_damage_withholds_previously_persisted_receipt(damage):
    register, retained = packet()
    sidecar = retained[facts.CAPTURE_FIELD]
    entry = next(iter(sidecar['paths'].values()))
    observed = retained['observations']['example.py']
    if damage == 'legacy': retained.pop(facts.CAPTURE_FIELD)
    elif damage == 'wrong_scope': retained['scope']['project_id'] = 'other'
    elif damage == 'wrong_hash': entry['source_sha256'] = 'b' * 64
    elif damage == 'wrong_oid': entry['blob_oid'] = 'b' * 40
    elif damage == 'wrong_line': entry['handlers'] = {'4': 'single_pass'}
    elif damage == 'wrong_kind': entry['handlers'] = {'3': 'single_continue'}
    elif damage == 'extra_text': entry['source_text'] = 'PRIVATE_SENTINEL'
    elif damage == 'malformed_map': entry['handlers'] = ['single_pass']
    elif damage == 'oversized': sidecar['paths']['x' * 5000] = entry
    elif damage == 'multiple_paths': sidecar['paths']['b' * 64] = entry
    elif damage == 'legacy_decoded': observed['source_binding']['origin'] = 'snapshot_decoded_text'
    elif damage == 'warning': observed['parse_warning_count'] = 1
    else: observed['complete_source_blob'] = False
    view = display_investigation(register, SCOPE, trusted_capture=retained)
    assert view['available'] and 'exception_handler' not in view['packets'][0]
    assert view['completed_count'] == 0


def test_receipt_is_not_self_authenticating_and_candidate_claims_are_ignored():
    register, retained = packet()
    assert 'exception_handler' not in display_investigation(register, SCOPE)['packets'][0]
    receipt = register['candidate_investigation']['packets'][0]['exception_handler']
    candidate = {**row(), 'exception_handler': deepcopy(receipt)}
    legacy = capture_sources({'example.py': PASS.decode()}, SCOPE, clock=lambda: 0)
    attempted = investigate_register({'findings': [candidate]}, legacy, SCOPE, clock=lambda: 0)
    assert 'exception_handler' not in attempted['packets'][0]
    receipt['body_kind'] = 'single_continue'
    assert 'exception_handler' not in display_investigation(register, SCOPE, trusted_capture=retained)['packets'][0]


def test_stale_fingerprint_and_forged_extra_receipt_fields_fail_closed():
    register, retained = packet()
    receipt = register['candidate_investigation']['packets'][0]['exception_handler']
    receipt['source_text'] = 'PRIVATE_SENTINEL'
    view = display_investigation(register, SCOPE, trusted_capture=retained)
    assert 'exception_handler' not in view['packets'][0] and 'PRIVATE_SENTINEL' not in str(view)
    register['findings'][0]['line'] = 99
    assert display_investigation(register, SCOPE, trusted_capture=retained)['available'] is False


def test_one_file_bound_and_original_selection_priority_are_preserved():
    rows = [row(), {**row(), 'candidate_id': 'b', 'source_path': 'other.py'},
            {**row(), 'candidate_id': 'assert', 'source_path': 'z.py', 'rule_id': 'B101', 'line': 1}]
    inventory, read, reads = memory({'example.py': PASS, 'other.py': PASS, 'z.py': b'assert x\n'})
    retained = collector.capture_candidates(rows, SCOPE, inventory, read, clock=lambda: 0)
    assert list(retained['observations']) == ['z.py', 'example.py', 'other.py']
    assert len(reads) == 3 and len(retained[facts.CAPTURE_FIELD]['paths']) == 1
    result = investigate_register({'findings': rows}, retained, SCOPE, clock=lambda: 0)
    assert ['exception_handler' in p for p in result['packets']] == [True, False, False]
    assert result['bounded_rule_analysis_completed'] == 1


def test_output_budget_optional_work_never_displaces_baseline(monkeypatch):
    rows = [{**row(), 'candidate_id': str(i), 'source_path': f'{i}.py'} for i in range(12)]
    files = {r['source_path']: PASS for r in rows}
    monkeypatch.setattr(collector, 'OUTPUT_LIMIT', 35000)
    inventory, read, baseline_reads = memory(files)
    with monkeypatch.context() as patch:
        patch.setattr(facts, 'eligible', lambda _: False)
        baseline = collector.capture_candidates(rows, SCOPE, inventory, read, clock=lambda: 0)
    inventory, read, current_reads = memory(files)
    current = collector.capture_candidates(rows, SCOPE, inventory, read, clock=lambda: 0)
    assert baseline_reads == current_reads
    assert current['observations'] == baseline['observations']
    assert current['source_bytes_read'] == baseline['source_bytes_read']
    assert current['unavailable_reasons'] == baseline['unavailable_reasons']
    assert len(current['observations']) < len(rows)
    assert len(collector.encoded(current)) <= collector.OUTPUT_LIMIT
    # Even an oversized optional extension is dropped before baseline fallback.
    monkeypatch.setattr(facts, 'make_capture', lambda *args: {'oversized': 'x' * 40000})
    inventory, read, _ = memory(files)
    overflow = collector.capture_candidates(rows, SCOPE, inventory, read, clock=lambda: 0)
    assert facts.CAPTURE_FIELD not in overflow and overflow['observations'] == baseline['observations']


def test_optional_deadline_overrun_does_not_lower_baseline_observation_population(monkeypatch):
    now = [0]
    rows = [row(), {**row(), 'candidate_id': 'b', 'source_path': 'later.py'}]
    files = {'example.py': PASS, 'later.py': PASS}
    inventory, read, reads = memory(files)
    def slow_optional(*args, **kwargs):
        assert len(reads) == 2  # Optional work only starts after baseline reads.
        now[0] = 6
        return {'3': 'single_pass'}
    monkeypatch.setattr(facts, 'observe_tree', slow_optional)
    retained = collector.capture_candidates(rows, SCOPE, inventory, read, clock=lambda: now[0])
    assert len(retained['observations']) == 2
    assert retained['unavailable_reasons'] == {} and retained['deadline_exhausted']
    assert facts.CAPTURE_FIELD not in retained


def test_extraction_bounds_and_ambiguous_ast_are_abstentions(monkeypatch):
    tree = ast.parse(PASS)
    tree.body[0].handlers.append(deepcopy(tree.body[0].handlers[0]))
    assert facts.observe_tree(tree, {3}, clock=lambda: 0, deadline=5) is None
    assert facts.observe_tree(ast.parse(PASS), {3}, clock=lambda: 5, deadline=5) is None
    monkeypatch.setattr(facts, 'MAX_NODES', 1)
    assert facts.observe_tree(ast.parse(PASS), {3}, clock=lambda: 0, deadline=5) is None


def test_receipt_total_count_and_byte_limits_never_change_completeness():
    rows = [{**row(), 'candidate_id': str(i)} for i in range(1000)]
    register, retained = packet(rows)
    issued = [p['exception_handler'] for p in register['candidate_investigation']['packets'] if 'exception_handler' in p]
    assert 0 < len(issued) <= facts.RECEIPT_COUNT_LIMIT
    assert sum(facts.encoded_size(item) for item in issued) <= facts.RECEIPT_TOTAL_BYTES
    view = display_investigation(register, SCOPE, trusted_capture=retained)
    assert view['completed_count'] == 0 and view['candidate_count'] == 1000


def test_no_second_parse_or_source_text_persistence(monkeypatch):
    source = PASS.replace(b'work()', b'work("PRIVATE_SENTINEL")')
    original = ast.parse
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(ast, 'parse', counted)
    register, retained = packet(source=source)
    assert calls == [1]
    assert 'PRIVATE_SENTINEL' not in json.dumps((register, retained))
    monkeypatch.setattr(ast, 'parse', lambda *args, **kwargs: pytest.fail('display must not parse'))
    assert 'exception_handler' in display_investigation(register, SCOPE, trusted_capture=retained)['packets'][0]


def test_real_git_collector_persistence_finalization_and_review_projection(tmp_path):
    from nico.comprehensive_review_work_v2 import review_work_projection
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path).decode().strip()
    git('init', '-q')
    (tmp_path / 'example.py').write_bytes(PASS)
    git('add', '.')
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'synthetic handler')
    sha = git('rev-parse', 'HEAD')
    scope = {**SCOPE, 'commit_sha': sha}
    (tmp_path / 'example.py').write_text('raise RuntimeError("must not execute")\n')
    scanner = [{'tool': 'bandit', 'category': 'static', 'status': 'completed', 'findings': [
        {'filename': 'example.py', 'line_number': 3, 'test_id': 'B110', 'issue_text': 'synthetic'}]}]
    retained = collector.capture_workspace(tmp_path, {**scope, 'snapshot_commit_sha': sha}, sha, scanner, env=os.environ.copy())
    candidate = row(); candidate['exact_commit_sha'] = sha
    register = {'findings': [candidate], 'candidate_record_count': 1,
                'review_workload_clusters': [{'cluster_id': 'synthetic', 'candidate_ids': [candidate['candidate_id']]}]}
    register['candidate_investigation'] = investigate_register(register, retained, scope)
    assert 'exception_handler' in register['candidate_investigation']['packets'][0]
    # JSON roundtrip models persistence without adding a database dependency.
    retained, register = json.loads(json.dumps([retained, register]))
    scoring = {'candidate_source_observations': retained, 'assessment': {'canonical_scanner_finding_register': register}}
    context = {**scope, 'prior_stage_results': {'evidence_reconciliation_and_scoring': scoring}}
    identity = {**scope, 'evidence_ledger_id': 'synthetic-ledger'}
    canonical = {'identity': identity, 'assessment': {'canonical_scanner_finding_register': deepcopy(register)}}
    before = deepcopy((register, canonical, retained))
    with final_investigation_scope(context):
        final = finalize_investigation(canonical)
    original = final['assessment']['canonical_scanner_finding_register']
    assert original['candidate_investigation'] == register['candidate_investigation']
    assert original['final_candidate_investigation']['bounded_rule_analysis_completed'] == 0
    record = {'identity': identity, 'stage_results': {'evidence_reconciliation_and_scoring': scoring,
              'final_comprehensive_report_generation': {'report_package': {'json': final}}}}
    projected = review_work_projection(record)
    packet_view = projected['review_assistance']['source_investigation']['packets'][0]
    assert packet_view['exception_handler']['source_sha256'] == hashlib.sha256(PASS).hexdigest()
    assert packet_view['completed'] is False and projected['client_delivery_allowed'] is False
    assert (register, canonical, retained) == before
