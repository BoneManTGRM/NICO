"""New capability, independent of the immutable historical Bitcoin reports."""
from pathlib import Path
import subprocess
import pytest

from nico import scanner_worker
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.repository_profile_coverage_v1 import profile_coverage


def test_cpp_complexity_analyzes_functions_and_preserves_population_identity():
    files = {
        'src/value.cpp': 'int value(int x) { if (x > 1) return x; return 0; }\n',
        'include/value.hpp': 'int value(int x);\n',
        'test/value.cpp': 'int main() { return 0; }\n',
        'src/helper.py': 'def helper(x):\n    return x\n',
    }
    measured = collect_complexity_evidence(files)
    assert measured['cpp_files_analyzed'] == 2
    assert measured['files_analyzed'] == 3
    assert measured['functions_measured'] == 2
    assert measured['maximum_cyclomatic_complexity'] == 2
    coverage = profile_coverage({'files': files, 'tree_paths': list(files),
        'tree_collection_succeeded': True, 'tree_truncated': False}, measured)
    assert coverage['eligible_source_files'] == 3
    assert coverage['observed_source_files'] == 4
    assert coverage['eligible_source_coverage_percent'] == 100
    assert coverage['whole_repository_coverage_percent'] == 75
    assert measured['cpp_analysis_method'] == 'lizard_token_function_analysis'
    assert measured['cpp_build_verified'] is False


def test_source_and_git_history_have_independent_bounded_sizes(tmp_path: Path):
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'pack').write_bytes(b'h' * 120)
    (tmp_path / 'core.cpp').write_bytes(b's' * 30)
    receipt = scanner_worker.repository_size_observation(tmp_path, source_limit=50, history_limit=150)
    assert receipt['source_bytes'] == 30
    assert receipt['git_history_bytes'] == 120
    assert receipt['inventory_complete'] is True
    assert receipt['exceeded_limits'] == []
    receipt = scanner_worker.repository_size_observation(tmp_path, source_limit=20, history_limit=100)
    assert receipt['exceeded_limits'] == ['source']
    assert receipt['byte_count_scope'] == 'lower_bound'
    receipt = scanner_worker.repository_size_observation(tmp_path, source_limit=50, history_limit=100)
    assert receipt['exceeded_limits'] == ['git_history']


def test_size_inventory_does_not_follow_external_symlinks(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'x' * 1000)
    (repo / 'outside.cpp').symlink_to(outside)
    receipt = scanner_worker.repository_size_observation(repo, source_limit=50, history_limit=150)
    assert receipt['source_bytes'] == len(str(outside).encode())
    assert receipt['symlink_count'] == 1
    assert receipt['external_symlink_targets_read'] is False


def test_unverified_size_does_not_claim_an_exceeded_limit(tmp_path: Path):
    from nico.snapshot_scanner_worker import RepositoryExecutionLimit
    observation = scanner_worker.repository_size_observation(tmp_path / 'absent')
    result = RepositoryExecutionLimit('a' * 40, 0, 150_000_000, size_observation=observation)
    assert result.evidence['reason'] == 'repository_size_unverified'
    assert 'exceeds' not in str(result).lower()
    assert result.evidence['size_population'] == 'unverified'


def test_public_git_profile_uses_full_bounded_source_budget(monkeypatch, tmp_path: Path):
    from nico import snapshot_repository_evidence as module
    origin = tmp_path / 'origin'
    origin.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=origin, check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init')
    for i in range(100):
        (origin / f'unit{i:03}.cpp').write_text('int value() { return 1; }\n')
    (origin / 'README.md').write_text('Repository documentation\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
    commit = git('rev-parse', 'HEAD')
    tree = git('rev-parse', 'HEAD^{tree}')
    monkeypatch.setattr(module.snapshot_capture, '_configure_public_origin',
        lambda path, url: subprocess.run(['git', 'remote', 'add', 'origin', str(origin)], cwd=path, check=True))
    # Local fixture transport replaces only acquisition, retaining real immutable
    # Git identity/tree/blob reads. Production's HTTPS-only policy is unchanged.
    monkeypatch.setattr(module.snapshot_capture, '_git_fetch_exact_sha',
        lambda path, sha, env, runner: subprocess.run(['git', 'fetch', '--depth=1', 'origin', sha],
            cwd=path, capture_output=True, text=True, check=False))
    profile, error = module._public_git_profile('generic/project', commit, tree)
    assert not error
    assert len([p for p in profile['files'] if p.endswith('.cpp')]) == 100
    assert profile['tree_sha'] == tree
    assert profile['source_profile']['source_files_loaded'] == 100
    assert profile['source_profile']['limit_excluded_paths'] == []


@pytest.mark.parametrize('include_python', [False, True])
def test_unmeasured_cpp_nesting_is_not_zero_or_score_credit(include_python):
    from nico.comprehensive_decision_grade_assessment_v6 import _architecture_control, _architecture_section
    from nico.full_assessment_complexity_score import apply_complexity_score
    files = {'src/value.cpp': 'int value(int x) { if(x) { if(x>1) { if(x>2) { if(x>3) { if(x>4) return x; } } } } return 0; }'}
    if include_python:
        files['src/helper.py'] = 'def helper(x):\n    return x\n'
    complexity = collect_complexity_evidence(files)
    complexity['run_id'] = 'synthetic_cpp_nesting'
    assert complexity['nesting_measured_functions'] == int(include_python)
    assert complexity['deep_nesting_functions'] == (0 if include_python else None)
    assessment = apply_complexity_score({'run_id': 'synthetic_cpp_nesting', 'sections': [
        {'id': 'velocity_complexity', 'score': 50, 'status': 'yellow'}]}, complexity)
    reasons = assessment['sections'][0]['score_evidence_breakdown']['reasons']
    assert not any('deep-nesting function ratio' in reason for reason in reasons)
    summary = assessment['complexity_artifact']['summary']
    assert summary['deep_nesting_functions'] == complexity['deep_nesting_functions']
    assert summary['nesting_measured_functions'] == int(include_python)
    control = _architecture_control(complexity)
    section = _architecture_section({}, complexity, control)
    text = ' '.join(section['evidence'])
    assert 'Deep nesting regions: 0.' not in text
    if include_python:
        assert '1/2' in text
    else:
        assert 'Deep nesting regions: not available' in text


def test_measured_python_nesting_keeps_existing_score_contract():
    from nico.full_assessment_complexity_score import apply_complexity_score
    complexity = collect_complexity_evidence({'src/helper.py': 'def helper(x):\n    return x\n'})
    complexity['run_id'] = 'synthetic_python_nesting'
    assessment = apply_complexity_score({'run_id': 'synthetic_python_nesting', 'sections': [
        {'id': 'velocity_complexity', 'score': 50, 'status': 'yellow'}]}, complexity)
    assert any('+1 deep-nesting function ratio' in reason
               for reason in assessment['sections'][0]['score_evidence_breakdown']['reasons'])


def test_cpp_architecture_and_analysis_use_the_same_source_population(monkeypatch):
    from nico import snapshot_repository_evidence as module
    from nico.storage import MemoryAdapter
    from tests.test_snapshot_repository_evidence import FakeSnapshotClient, _context, _snapshot
    client = FakeSnapshotClient()
    client.files = {'src/value.cpp': 'int value(int x) { return x; }\n',
                    'include/value.hpp': 'int value(int x);\n'}
    profile = {'files': client.files, 'tree_paths': sorted(client.files), 'root_items': ['src', 'include'],
               'unavailable': [], 'unavailable_paths': [], 'tree_sha': 'b' * 40,
               'tree_collection_succeeded': True, 'tree_truncated': False}
    monkeypatch.setattr(module, '_profile', lambda *args: profile)
    monkeypatch.setattr(module, '_public_git_profile', lambda *args: (profile, ''))
    class SyntheticStore(MemoryAdapter):
        def audit(self, *args, **kwargs):
            return None
    store = SyntheticStore()
    context = _context()
    snapshot = _snapshot(context)
    repository, complexity = module.collect_snapshot_repository_evidence(context, snapshot, client=client, store=store)
    assert repository['snapshot_commit_sha'] == complexity['snapshot_commit_sha'] == snapshot['commit_sha']
    assert complexity['cpp_files_analyzed'] == 2
    assert repository['architecture_evidence']['source_file_count'] == 2
    assert complexity['profile_coverage']['observed_source_files'] == 2
    assert complexity['profile_coverage']['eligible_source_files'] == 2


@pytest.mark.parametrize('include_python', [False, True])
def test_cpp_unknown_and_subset_nesting_have_spanish_presentation(include_python):
    from nico.comprehensive_decision_grade_assessment_v6 import _architecture_control, _architecture_section
    from nico.full_assessment_complexity_score import apply_complexity_score
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    files = {'src/value.cpp': 'int value(int x) { return x; }\n'}
    if include_python:
        files['src/helper.py'] = 'def helper(x):\n    return x\n'
    complexity = collect_complexity_evidence(files)
    complexity['run_id'] = 'synthetic_cpp_spanish'
    architecture = _architecture_section({}, complexity, _architecture_control(complexity))
    assessment = apply_complexity_score({'run_id': complexity['run_id'], 'sections': [
        {'id': 'velocity_complexity', 'score': 50, 'status': 'yellow'}]}, complexity)
    velocity = assessment['sections'][0]
    nesting = next(line for line in architecture['evidence'] if line.startswith('Deep nesting regions:'))
    localized = spanish._translate_presentation_field(nesting, 'evidence')
    assert 'anidamiento' in localized and 'Deep nesting' not in localized
    assert ('1/2' in localized) if include_python else ('no disponible' in localized)
    assert 'sin ajuste' in spanish._translate_presentation_field(velocity['summary'], 'summary')
    hotspot = next(line for line in velocity['evidence'] if line.startswith('Complexity hotspots:'))
    assert 'anidamiento' in spanish._translate_presentation_field(hotspot, 'evidence')
    note = next(line for line in complexity['unavailable_data_notes'] if line.startswith('C/C++ function complexity'))
    translated_note = spanish._translate_presentation_field(note, 'unavailable')
    assert 'Lizard' in translated_note and 'sin compilación ni evaluación de seguridad' in translated_note
    # Exercise the public entry point whose fail-closed localization precedes PDF/Markdown layout.
    spanish.render_spanish_markdown({'identity': {}, 'assessment': {'sections': [
        {'id': 'architecture_debt', 'label': 'Architecture & Technical Debt', 'evidence': [nesting]}]},
        'stage_summaries': []})


def test_cpp_spanish_contract_rejects_unknown_nesting_prose():
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    with pytest.raises(ValueError):
        spanish._translate_presentation_field('Deep nesting regions: invented completion claim.', 'evidence')
