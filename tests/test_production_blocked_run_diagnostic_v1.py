from pathlib import Path
import json
import httpx
import pytest
from scripts.production_blocked_run_diagnostic_v1 import diagnose, source_catalog

RUN = 'comprun_' + 'a' * 32
COMMIT = 'b' * 40
SECRET = 'private-session-do-not-retain'

def payload():
    return {'run_id': RUN, 'commit_sha': COMMIT, 'status': 'blocked', 'terminal': True,
        'client_delivery_allowed': False, 'current_stage': 'final_comprehensive_report_generation',
        'record': {'stage_results': {'final_comprehensive_report_generation': {
            'status': 'blocked', 'reason': 'final_report_provider_failed',
            'error_message': 'Canonical artifact is not valid: ' + SECRET,
            'secret': SECRET}}}, 'customer_id': SECRET}

def call(value, status=200):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=value, headers={'Location': 'https://evil.invalid/'})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        result = diagnose(client=client, run_id=RUN, expected_commit=COMMIT,
            codes={'final_report_provider_failed'}, fragments=[('unit.py', 12, 'Canonical artifact is not valid: ')])
    return result, seen

def test_retains_only_static_diagnostic_fragments():
    result, requests = call(payload())
    assert len(requests) == 1 and requests[0].method == 'GET'
    assert requests[0].url.host == 'app.nicoaudit.com'
    assert result['production_modified'] is False and result['shipping_clearance'] is False
    assert result['failure']['reason'] == 'final_report_provider_failed'
    assert len(result['failure']['message_sha256']) == 64
    assert result['failure']['source_literal_matches'][0]['text'] == 'Canonical artifact is not valid: '
    assert SECRET not in json.dumps(result)

@pytest.mark.parametrize('status', [302, 401, 403, 409, 500])
def test_failed_read_never_qualifies(status):
    with pytest.raises(ValueError, match='diagnostic_http'):
        call(payload(), status)

@pytest.mark.parametrize('field,value', [('run_id', 'other'), ('commit_sha', 'c'*40),
    ('terminal', False), ('status', 'running'), ('client_delivery_allowed', True)])
def test_identity_and_state_must_match(field, value):
    data = payload(); data[field] = value
    with pytest.raises(ValueError): call(data)

def test_unrecognized_code_does_not_leak():
    data = payload(); data['record']['stage_results']['final_comprehensive_report_generation']['reason'] = SECRET
    result, _ = call(data)
    assert result['failure']['reason'] == 'unrecognized'
    assert SECRET not in json.dumps(result)

def test_invalid_input_makes_no_request():
    def handler(_): raise AssertionError('No request allowed')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            diagnose(client=client, run_id='../foreign', expected_commit=COMMIT, codes=set(), fragments=[])

def test_catalog_reads_literals_without_running_source(tmp_path):
    (tmp_path/'sample.py').write_text('raise RuntimeError("Canonical artifact is not valid: " + unknown)\ncode = "final_report_provider_failed"\n')
    codes, fragments = source_catalog(tmp_path)
    assert 'final_report_provider_failed' in codes
    assert any(text == 'Canonical artifact is not valid: ' for _, _, text in fragments)


def test_diagnostic_workflow_cannot_publish_a_release_success():
    import yaml
    path = Path(__file__).parents[1] / '.github/workflows/spanish-comprehensive-production-proof.yml'
    workflow = yaml.safe_load(path.read_text())
    jobs = workflow['jobs']
    assert 'diagnostic_run_id' in jobs['spanish-comprehensive']['if']
    job = jobs['blocked-run-diagnostic']
    assert job['permissions'] == {'contents': 'read', 'id-token': 'write'}
    assert job['steps'][-1]['if'] == 'always()'
    assert job['steps'][-1]['run'].rstrip().endswith('exit 1')
    assert 'blocked-run-diagnostic-' in job['steps'][-2]['with']['name']
    assert all('/continue' not in str(step) for step in job['steps'])
