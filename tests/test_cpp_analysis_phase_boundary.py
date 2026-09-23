"""Analysis outputs must be separated from the assessed process identity."""
from copy import deepcopy

from nico.assessment_cpp_full_project_execution import boundary_valid
from tests.test_assessment_cpp_full_project import native, plan


def test_full_project_boundary_requires_private_analysis_directory():
    boundary = deepcopy(native()['boundary'])
    boundary.pop('analysis_private', None)
    assert boundary_valid(boundary) is False


def test_full_project_analyzer_does_not_share_target_writable_artifacts():
    from nico.assessment_cpp_full_project import execution_steps
    step = next(s for s in execution_steps(plan()) if s['id'] == 'static-analysis')
    assert '--project=/work/analysis/compile_commands.json' in step['invocation']
    assert step['artifacts']['analysis_xml'] == '/work/analysis/cppcheck.xml'
    assert step['artifacts']['compilation_database'] == '/work/analysis/compile_commands.json'


def test_branch_analysis_limit_is_retained_and_cannot_claim_completion():
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    result = native()
    analysis = next(s for s in result['steps'] if s['id'] == 'static-analysis')
    analysis['artifacts']['analysis_xml'] = encoded(
        b'<results version="2"><cppcheck version="2.17.1"/><errors>'
        b'<error id="normalCheckLevelMaxBranches" severity="information" '
        b'msg="Limiting analysis of branches."/></errors></results>')
    parsed = validate_native(result, plan())
    assert parsed['complete'] is False
    assert parsed['status'] == 'partial'
    assert any(r['rule_id'] == 'normalCheckLevelMaxBranches' for r in parsed['coverage']['limitations'])


def test_full_project_requests_exhaustive_analysis_instead_of_suppressing_limits():
    from nico.assessment_cpp_full_project import execution_steps
    analysis = next(s for s in execution_steps(plan()) if s['id'] == 'static-analysis')
    assert '--check-level=exhaustive' in analysis['invocation']
    assert not any(x.startswith('--suppress') for x in analysis['invocation'])


def test_analyzer_cannot_claim_frozen_configuration_after_database_substitution():
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    value = native()
    row = next(s for s in value['steps'] if s['id'] == 'static-analysis')
    row['artifacts']['compilation_database'] = encoded(b'[]')
    outcome = validate_native(value, plan())
    assert outcome['complete'] is False
    assert outcome['build']['analysis_artifact_isolation_verified'] is False


def test_failed_write_denial_observation_prevents_complete_analysis():
    from nico.assessment_cpp_full_project import validate_native
    value = native()
    value['boundary']['analysis_write_denied'] = False
    assert validate_native(value, plan())['complete'] is False


def test_analyzer_uses_separate_uid_for_command_and_artifact_collection(tmp_path):
    from nico.assessment_cpp_full_project_execution import run_full_project, READ_PROGRAM
    from tests.test_assessment_cpp_full_project import FakeDocker, source_fixture
    contract = source_fixture(tmp_path)
    fake = FakeDocker(contract, native(contract))
    result = run_full_project(contract, tmp_path, checkpoint=lambda: None, timeout_seconds=60, command=fake)
    assert result['native']['error'] is None
    static_calls = [argv for argv, _ in fake.calls if 'cppcheck' in argv or
        (READ_PROGRAM in argv and '/work/analysis/' in argv[-2])]
    assert len(static_calls) == 4
    assert all('--user=1001:1001' in argv for argv in static_calls)
    build_calls = [argv for argv, _ in fake.calls if 'cmake' in argv or 'ctest' in argv]
    assert build_calls and all('--user=1001:1001' not in argv for argv in build_calls)


def test_nonstring_native_error_is_rejected_as_bad_evidence():
    import pytest
    from nico.assessment_cpp_full_project import validate_native
    for invalid in ([], {}, 1, True):
        value = native(); value['error'] = invalid
        with pytest.raises(ValueError):
            validate_native(value, plan())
