import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.verify_cpp_collection_tool_export import verify


@pytest.fixture
def exported(tmp_path):
    files = {'cppcheck': b'synthetic analyzer, never executed', 'COPYING': b'license',
             'repair.json': b'{}', 'nico-clang-header-observer.so': b'synthetic plugin',
             'cfg/std.cfg': b'model', 'platforms/unix64.xml': b'platform',
             'image-config-digest.txt': ('sha256:' + 'a' * 64).encode(),
             'image.json': json.dumps([{'Id': 'sha256:' + 'a' * 64}]).encode()}
    files['clang-header-observer.json'] = json.dumps({
        'schema': 'nico.clang-header-tool.v1',
        'plugin_sha256': hashlib.sha256(files['nico-clang-header-observer.so']).hexdigest(),
    }).encode()
    for name, raw in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return tmp_path


def test_manifest_binds_all_bytes_to_collection_image_without_execution(exported):
    result = verify(exported)
    assert result['image_config_digest'] == 'sha256:' + 'a' * 64
    assert result['qualification_completed'] is False
    for name, record in result['files'].items():
        raw = (exported / name).read_bytes()
        assert record == {'size_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize('fault', ['plugin', 'image', 'missing', 'models', 'symlink', 'oversize'])
def test_invalid_exports_fail_closed(exported, fault):
    if fault == 'plugin':
        (exported / 'nico-clang-header-observer.so').write_bytes(b'wrong plugin')
    elif fault == 'image':
        (exported / 'image-config-digest.txt').write_text('sha256:' + 'b' * 64)
    elif fault == 'missing':
        (exported / 'cppcheck').unlink()
    elif fault == 'models':
        (exported / 'cfg/std.cfg').unlink()
    elif fault == 'symlink':
        (exported / 'cfg/link').symlink_to(exported / 'cppcheck')
    else:
        with (exported / 'nico-clang-header-observer.so').open('wb') as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match='collection_export_'):
        verify(exported)


def collection_steps():
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    return workflow['jobs']['project-baseline-qualification']['steps']


def test_collection_exports_its_own_stopped_image_and_uploads_even_on_failure():
    steps = collection_steps()
    provision = next(step for step in steps if step.get('id') == 'collection_image')
    export = next(step for step in steps if step.get('id') == 'collection_tool_retention')
    script = export['run']
    assert 'cpp-collection-toolchain' not in provision['run']
    assert 'docker create --network=none --read-only --entrypoint=/bin/true "$(cat full-project-image-id.txt)"' in script
    assert 'docker start' not in script and 'docker run' not in script
    for source, destination in [('/usr/local/bin/cppcheck', 'cppcheck'),
                                ('/opt/nico-clang-header-observer.so', 'nico-clang-header-observer.so')]:
        assert f'docker cp "$toolchain_container:{source}" cpp-collection-toolchain.pending/{destination}' in script
    assert 'cp full-project-image-id.txt cpp-collection-toolchain.pending/image-config-digest.txt' in script
    assert 'verify_cpp_collection_tool_export --directory cpp-collection-toolchain.pending' in script
    collect = next(step for step in steps if '--accept-completed-collection' in step.get('run', ''))
    assert '--image "$(cat full-project-image-id.txt)"' in collect['run']
    upload = next(step for step in steps if 'upload-artifact@' in step.get('uses', ''))
    assert steps.index(provision) < steps.index(collect) < steps.index(export) < steps.index(upload)
    assert export['if'] == "${{ always() && steps.collection_image.outcome == 'success' }}"
    assert not export.get('continue-on-error')
    assert upload['if'] == 'always()'
    assert 'cpp-baseline-qualification/' in upload['with']['path'].splitlines()
    assert 'cpp-collection-toolchain/' in upload['with']['path'].splitlines()
    assert 'cpp-collection-toolchain-manifest.json' in upload['with']['path'].splitlines()
    assert script.index('verify_cpp_collection_tool_export') < script.index('mv cpp-collection-toolchain.pending cpp-collection-toolchain')
    assert '.pending' not in upload['with']['path']
    assert 'cpp-baseline-qualification' not in script


@pytest.mark.parametrize('image,collection,retention,expected_export', [
    ('success', 'success', 'success', True),
    ('success', 'failure', 'success', True),
    ('success', 'failure', 'failure', True),
    ('success', 'success', 'failure', True),
    ('failure', 'skipped', 'skipped', False),
])
def test_evidence_retention_failure_paths(image, collection, retention, expected_export):
    # Evaluate the exact restricted condition from YAML, not a replacement workflow.
    steps = collection_steps()
    export = next(step for step in steps if step.get('id') == 'collection_tool_retention')
    expression = export['if'].removeprefix('${{ ').removesuffix(' }}')
    expression = expression.replace('always()', 'True').replace('&&', 'and')
    expression = expression.replace('steps.collection_image.outcome', repr(image))
    assert eval(expression, {'__builtins__': {}}, {}) is expected_export
    upload = next(step for step in steps if 'upload-artifact@' in step.get('uses', ''))
    assert upload['if'] == 'always()'  # Independent of both failure outcomes.
    assert not export.get('continue-on-error')  # A retention failure remains visible.
    assert 'cpp-baseline-qualification/' in upload['with']['path'].splitlines()


def test_failed_validation_preserves_primary_evidence_and_export_bytes(exported):
    evidence = exported.parent / 'cpp-baseline-qualification'
    evidence.mkdir()
    finding = evidence / 'findings.json'
    finding.write_text('{"compiler":"generated #error","ubsan":"streams.cpp:99:24"}')
    (exported / 'nico-clang-header-observer.so').write_bytes(b'mismatched synthetic plugin')
    before = {p: p.read_bytes() for p in exported.parent.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='collection_export_observer_mismatch'):
        verify(exported)
    assert {p: p.read_bytes() for p in before} == before
