"""Local immutable-checkout fixtures; no provider calls or project commands."""
from pathlib import Path

import pytest

from nico.hosted_provider_comprehensive_runtime_v1 import _profile_checkout
from nico.hosted_assessment import KNOWN_FILE_PATHS, MAX_FILE_BYTES, MAX_TEXT_FILES
from nico.repository_profile_coverage_v1 import profile_coverage
from nico.full_assessment_complexity_evidence import collect_complexity_evidence


def write(root, files):
    for path, text in files.items():
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


@pytest.mark.parametrize('path', ['files/js/application.js', 'arbitrary/deep/module.ts',
    'packages/widget/view.jsx', 'packages/widget/view.tsx', 'services/custom/handler.py',
    'arbitrary/deep/compound.module.ts'])
def test_nested_supported_source_uses_available_profile_slots(tmp_path, path, monkeypatch):
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false')
    source = 'const answer = 42;\n' if not path.endswith('.py') else 'answer = 42\n'
    files = {'README.md': '# synthetic\n', **{f'docs/note{i}.md': 'metadata' for i in range(12)}, path: source}
    write(tmp_path, files)
    before = {p: (tmp_path/p).read_bytes() for p in files}
    profile = _profile_checkout(tmp_path)
    assert profile['files'][path] == source
    assert len(profile['files']) == 14 < MAX_TEXT_FILES
    assert profile['tree_paths'] == sorted(files)
    assert profile['tree_collection_succeeded'] is True
    assert {p: (tmp_path/p).read_bytes() for p in files} == before
    # Acquisition alone is never credited as analyzer execution.
    coverage = profile_coverage(profile, {'files_analyzed': 0, 'analyzed_source_paths': []})
    assert coverage['eligible_source_files'] == 1
    assert coverage['sampled_eligible_source_files'] == 1
    assert coverage['analyzed_source_files'] == 0
    assert coverage['sampled_unanalyzed_source_paths'] == [path]
    assert coverage['unsampled_eligible_source_files'] == 0


def test_metadata_priority_sorted_selection_and_real_analysis_accounting(tmp_path):
    files = {'README.md': '# fixture', 'package.json': '{}',
             **{f'arbitrary/deep/module{i:03}.py': 'answer = 42\n' for i in range(100)}}
    write(tmp_path, dict(reversed(list(files.items()))))
    before = {p: (tmp_path/p).read_bytes() for p in files}
    profile = _profile_checkout(tmp_path)
    priority = [p for p in KNOWN_FILE_PATHS if p in files]
    selected = (priority + sorted(set(files)-set(priority)))[:90]
    assert MAX_TEXT_FILES == 90 and MAX_FILE_BYTES == 240000
    assert list(profile['files']) == selected
    assert _profile_checkout(tmp_path) == profile
    measured = collect_complexity_evidence(profile['files'])
    coverage = profile_coverage(profile, measured)
    sampled = len(selected)-len(priority)
    assert coverage['eligible_source_files'] == 100
    assert coverage['sampled_eligible_source_files'] == sampled
    assert coverage['analyzed_source_files'] == sampled
    assert coverage['unsampled_eligible_source_files'] == 100-sampled
    assert coverage['sampled_unanalyzed_source_paths'] == []
    assert coverage['absence_of_findings_proven'] is False
    assert {p: (tmp_path/p).read_bytes() for p in files} == before


def test_fallback_preserves_excluded_generated_vendor_and_unsupported_paths(tmp_path):
    excluded = ['deep/node_modules/module.js', 'deep/vendor/module.ts', 'deep/dist/module.js',
        'deep/build/module.py', 'deep/.next/module.tsx', 'deep/.venv/module.py',
        'deep/coverage/module.js', 'deep/__pycache__/module.py', 'deep/assets/bundle.min.js',
        'deep/assets/bundle.min.jsx', 'deep/assets/image.png', 'deep/custom/source.rb']
    write(tmp_path, {path: 'not eligible' for path in excluded})
    profile = _profile_checkout(tmp_path)
    assert profile['files'] == {}
    assert profile['tree_paths'] == sorted(excluded)


@pytest.mark.parametrize('files', [{}, {'nested/unsupported/source.rb': 'puts 1'}])
def test_empty_or_unsupported_checkout_does_not_invent_source_coverage(tmp_path, files):
    write(tmp_path, files)
    profile = _profile_checkout(tmp_path)
    coverage = profile_coverage(profile, collect_complexity_evidence(profile))
    assert profile['files'] == {}
    assert coverage['eligible_source_files'] == coverage['analyzed_source_files'] == 0
    assert coverage['eligible_source_coverage_percent'] is None


def test_nested_size_limit_and_symlinks_remain_unavailable(tmp_path):
    write(tmp_path, {'deep/custom/exact.py': ' '*MAX_FILE_BYTES,
                     'deep/custom/large.py': ' '*(MAX_FILE_BYTES+1)})
    outside = tmp_path.parent/(tmp_path.name+'-outside')
    outside.mkdir(); (outside/'secret.py').write_text('DO_NOT_READ')
    (tmp_path/'linked').symlink_to(outside, target_is_directory=True)
    (tmp_path/'deep/custom/link.py').symlink_to(outside/'secret.py')
    profile = _profile_checkout(tmp_path)
    assert profile['files'] == {'deep/custom/exact.py': ' '*MAX_FILE_BYTES}
    assert profile['size_excluded_paths'] == ['deep/custom/large.py']
    assert {'linked', 'deep/custom/link.py'} <= set(profile['unavailable_paths'])
    assert 'linked/secret.py' not in profile['tree_paths']
    assert 'DO_NOT_READ' not in str(profile)


def test_nested_file_growth_during_read_is_not_credited(tmp_path, monkeypatch):
    write(tmp_path, {'deep/custom/growing.py': 'x=1'})
    original = Path.open
    def growing(path, *args, **kwargs):
        if path == tmp_path/'deep/custom/growing.py' and args == ('rb',):
            with original(path, 'wb') as output: output.write(b'x'*(MAX_FILE_BYTES+1))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', growing)
    profile = _profile_checkout(tmp_path)
    assert profile['files'] == {}
    assert profile['unavailable_paths'] == ['deep/custom/growing.py']
