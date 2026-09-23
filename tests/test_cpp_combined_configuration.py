"""Generated contexts and published immutable binary replay must compose.

These observations are synthetic schema fixtures, not native execution proof.
"""
from copy import deepcopy
import json
import pytest

from nico.assessment_cpp_full_project import configuration, execution_steps, validate_native
from nico.assessment_worker_receipts import validate_contract, validate_receipt
from tests.test_assessment_cpp_full_project import wrap, encoded
from tests.test_cpp_generated_context import v3_fixture as generated_fixture, HEADERS
from tests.test_cpp_native_test_binding import v3_fixture as replay_fixture, discovery, proof
from scripts.worker_protocol_fixture import identity


def combined_fixture():
    contract, native = generated_fixture()
    contract['configuration']['native_test_evidence'] = 'bound-binary-replay-v1'
    existing = {row['id']: row for row in native['steps']}
    native['steps'] = []
    for spec in execution_steps(contract):
        row = existing.get(spec['id'])
        if row is None:
            group = spec['native_test_configuration']
            row = dict(id=spec['id'], invocation=spec['invocation'], attempted=True,
                       exit_code=0, timed_out=False, output_truncated=False,
                       duration_ms=1, output=encoded(json.dumps(proof(group=group)).encode()), artifacts={})
        if spec['id'] in {'address-discover', 'undefined-discover'}:
            row['output'] = encoded(discovery(group=spec['id'].split('-')[0]))
        native['steps'].append(row)
    return contract, native


def test_published_v3_remains_native_replay_not_a_generated_context_contract():
    contract, native = replay_fixture()
    before = deepcopy(contract)
    assert contract['configuration']['schema'] == 'nico.cpp-cmake-configuration.v3'
    assert validate_contract(contract) == before
    result = validate_native(native, contract)
    assert result['build']['implemented_command_scope_complete'] is True
    assert 'generated_context' not in result['build']
    assert set(result['build']['native_test_binary_evidence']) == {'address', 'undefined'}
    assert not any('generated_configuration' in row for row in execution_steps(contract))
    assert contract == before


@pytest.mark.parametrize('enabled', [False, True])
def test_v4_explicitly_selects_generated_and_native_evidence_without_implicit_activation(enabled):
    result = configuration(units=['main.cpp', 'sum.cpp'], unit_tests=['unit'],
        integration_tests=['integration'], compiler_evidence=True,
        native_test_evidence=enabled, generated_headers=HEADERS)
    assert result['schema'] == 'nico.cpp-cmake-configuration.v4'
    assert result['native_test_evidence'] == ('bound-binary-replay-v1' if enabled else 'not_requested')
    contract, _ = generated_fixture(); contract['configuration'] = result
    assert validate_contract(contract) == contract
    steps = execution_steps(contract)
    assert sum('generated_configuration' in row for row in steps) == 3
    assert sum('native_test_configuration' in row for row in steps) == (2 if enabled else 0)


def test_combined_v4_publishes_both_evidence_populations_without_claiming_bitcoin():
    contract, native = combined_fixture()
    before = deepcopy(native)
    receipt = wrap(native, contract)
    _, record, _ = validate_receipt(identity(contract), contract,
        receipt['lease_id'], receipt['worker_id'], receipt)
    build = record['cpp_build_evidence']
    assert build['implemented_command_scope_complete'] is True
    assert set(build['generated_context']) == {'baseline', 'address', 'undefined'}
    for group in ('address', 'undefined'):
        assert build['native_test_binary_evidence'][group]['binary_instrumentation_verified'] is True
        assert build['sanitizers'][group]['instrumentation_verified'] is False
        assert build['sanitizers'][group]['isolated_binary_replay_verified'] is True
        assert build['compiler_evidence'][group]['generated_header_inclusions']
    assert build['full_project_qualified'] is False and build['fuzz_executed'] is False
    assert record['client_delivery_allowed'] is False
    assert native == before


@pytest.mark.parametrize('missing', ['address-generated-context', 'address-native-test-evidence'])
def test_missing_either_required_proof_keeps_combined_command_scope_incomplete(missing):
    contract, native = combined_fixture()
    row = next(r for r in native['steps'] if r['id'] == missing)
    row.update(attempted=False, exit_code=None, duration_ms=0, output='', artifacts={})
    # Compiler evidence cannot be retained without its upstream capture.
    if missing.endswith('generated-context'):
        row = next(r for r in native['steps'] if r['id'] == 'address-compiler-evidence')
        row.update(attempted=False, exit_code=None, duration_ms=0, output='', artifacts={})
    result = validate_native(native, contract)
    assert result['build']['implemented_command_scope_complete'] is False
    assert result['build']['full_project_qualified'] is False


@pytest.mark.parametrize('value', [True, False, None, 1, {}, [], 'unknown'])
def test_v4_native_mode_rejects_malformed_values(value):
    contract, _ = combined_fixture()
    contract['configuration']['native_test_evidence'] = value
    with pytest.raises(ValueError): validate_contract(contract)


def test_generated_fields_cannot_be_smuggled_into_old_v3_schema():
    contract, _ = combined_fixture()
    contract['configuration']['schema'] = 'nico.cpp-cmake-configuration.v3'
    with pytest.raises(ValueError): validate_contract(contract)


def test_owned_integration_plan_keeps_binary_proof_enabled_with_generated_headers():
    from scripts.qualify_cpp_full_project_integration import plan
    contract = plan('sha256:' + 'd' * 64, generated_headers=True)
    assert contract['configuration']['schema'] == 'nico.cpp-cmake-configuration.v4'
    assert contract['configuration']['native_test_evidence'] == 'bound-binary-replay-v1'
    assert validate_contract(contract) == contract


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_combined_report_discloses_generated_headers_and_isolated_binary_replays(tmp_path, language):
    from nico.assessment_worker_jobs import _digest
    from scripts.qualify_cpp_full_project_integration import render_result
    contract, native = combined_fixture()
    receipt = wrap(native, contract)
    _, record, _ = validate_receipt(identity(contract), contract,
        receipt['lease_id'], receipt['worker_id'], receipt)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(receipt))
    result = render_result({'canonical_record': record}, tmp_path, language)
    content = (tmp_path / ('owned-project-' + language + '.md')).read_text()
    assert ('Generated headers:' if language == 'en' else 'Encabezados generados:') in content
    assert ('Isolated binary replays' if language == 'en' else 'Repeticiones aisladas de binarios') in content
    assert result['automated_draft'] is True
    assert result['production_report'] is False
