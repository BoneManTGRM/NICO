"""Frozen public-checkout configuration qualification, not production acceptance.

Source capture uses the complete local Git tree. Target commands run only
inside a digest-bound disposable image. Configure-only is the default; the
explicit baseline contract adds a bounded complete build and discovered tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from nico.assessment_worker_receipts import canonical_bytes

def freeze_configuration_checkout(checkout, destination, manifest):
    """Verify every pinned Git entry; materialize original regular blobs only.

    Git is used solely to read local object metadata. No target command, hook,
    dependency install, source helper, fetch, or submodule operation runs here.
    Symlinks/gitlinks stay explicit inventory exclusions, never followed.
    """
    import re
    from pathlib import PurePosixPath
    from nico.assessment_cpp_full_project import MAX_SOURCE_BYTES, MAX_FILE_BYTES
    from nico.assessment_worker_container import _command, _read_input
    fields = {'schema', 'repository', 'commit_sha', 'tree_sha', 'inventory', 'project_options'}
    if (not isinstance(manifest, dict) or set(manifest) != fields
            or manifest['schema'] != 'nico.cpp-configuration-benchmark.v1'
            or not isinstance(manifest['repository'], str)
            or re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', manifest['repository']) is None
            or any(not isinstance(manifest[k], str) or re.fullmatch(r'[a-f0-9]{40}', manifest[k]) is None
                   for k in ('commit_sha', 'tree_sha'))
            or not isinstance(manifest['inventory'], dict)
            or set(manifest['inventory']) != {'entries', 'blobs', 'source_bytes'}
            or any(type(v) is not int or v < 1 for v in manifest['inventory'].values())
            or manifest['inventory']['entries'] > 20000
            or manifest['inventory']['blobs'] > manifest['inventory']['entries']
            or manifest['inventory']['source_bytes'] > MAX_SOURCE_BYTES):
        raise ValueError('qualification_manifest_invalid')
    checkout, destination = Path(checkout).absolute(), Path(destination).absolute()
    if (checkout.is_symlink() or not checkout.is_dir() or checkout != checkout.resolve(strict=True)
            or destination.exists() or destination.is_symlink()
            or destination.parent != destination.parent.resolve(strict=True)):
        raise ValueError('qualification_source_path_invalid')
    start = time.monotonic()
    def checkpoint():
        if time.monotonic()-start >= 20: raise ValueError('qualification_acquisition_deadline')
    def git(*args):
        return _command(['git', '--no-replace-objects', '-c', 'core.fsmonitor=false',
            '-c', 'core.hooksPath=/dev/null', '-C', str(checkout), *args], checkpoint=checkpoint,
            timeout=10, limit=8*1024*1024)
    if (git('rev-parse', 'HEAD').decode().strip() != manifest['commit_sha']
            or git('rev-parse', 'HEAD^{tree}').decode().strip() != manifest['tree_sha']):
        raise ValueError('qualification_checkout_identity_mismatch')
    raw_tree = git('ls-tree', '-r', '-t', '-l', '-z', '--full-tree', manifest['commit_sha'])
    inventory, targets, seen, total, materialized_bytes, blob_count = [], {}, set(), 0, 0, 0
    root_fd = os.open(checkout, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with tempfile.TemporaryDirectory(prefix='.qualification-', dir=destination.parent) as tmp:
            staged = Path(tmp)/'inputs'; staged.mkdir(mode=0o700)
            for encoded in raw_tree.split(b'\0'):
                if not encoded: continue
                checkpoint()
                metadata, raw_path = encoded.split(b'\t', 1)
                mode, kind, blob, size = metadata.decode('ascii').split()
                path = raw_path.decode('utf-8')
                if (not path or len(path)>1000 or PurePosixPath(path).is_absolute()
                        or PurePosixPath(path).as_posix()!=path or ':' in path or '\\' in path
                        or any(part in {'', '.', '..', '.git'} for part in path.split('/'))
                        or any(ord(c)<32 for c in path) or re.fullmatch(r'[a-f0-9]{40}',blob) is None
                        or path in seen):
                    raise ValueError('qualification_inventory_path_invalid')
                seen.add(path)
                row={'path':path,'git_mode':mode,'git_type':kind,'git_blob':blob,
                     'bytes':int(size) if size!='-' else None,'materialized':False,'exclusion':None}
                inventory.append(row)
                if len(inventory)>manifest['inventory']['entries']:
                    raise ValueError('qualification_inventory_population_mismatch')
                if kind=='tree' and mode=='040000': continue
                if kind=='commit' and mode=='160000':
                    row['exclusion']='unmaterialized_gitlink'; continue
                if kind!='blob' or type(row['bytes']) is not int or not 0<=row['bytes']<=MAX_FILE_BYTES:
                    raise ValueError('qualification_inventory_type_or_size_invalid')
                total += row['bytes']; blob_count += 1
                if total>MAX_SOURCE_BYTES: raise ValueError('qualification_source_budget')
                if mode=='120000':
                    row['exclusion']='unmaterialized_symlink'
                    # A required C/C++ entry may not disappear from a source inventory.
                    if Path(path).suffix.lower() in {'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx'}:
                        raise ValueError('qualification_required_source_symlink')
                    continue
                if mode not in {'100644','100755'}: raise ValueError('qualification_inventory_mode_invalid')
                data=_read_input(root_fd,path,MAX_FILE_BYTES)
                actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data,usedforsecurity=False).hexdigest()
                if len(data)!=row['bytes'] or actual!=blob:
                    raise ValueError('qualification_source_digest_mismatch')
                if data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
                    row['exclusion']='git_lfs_pointer_not_fetched'
                    if Path(path).suffix.lower() in {'.c','.cc','.cpp','.cxx','.h','.hh','.hpp','.hxx'}:
                        raise ValueError('qualification_required_source_lfs')
                    continue
                targets[path]=hashlib.sha256(data).hexdigest()
                materialized_bytes += len(data)
                target=staged/path; target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as handle: handle.write(data)
                target.chmod(0o555 if mode=='100755' else 0o444)
                row['materialized']=True; row['sha256']=targets[path]
            observed={'entries':len(inventory),'blobs':blob_count,'source_bytes':total}
            if observed!=manifest['inventory'] or 'CMakeLists.txt' not in targets:
                raise ValueError('qualification_inventory_population_mismatch')
            receipt={'schema':'nico.cpp-configuration-source.v1','repository':manifest['repository'],
                'commit_sha':manifest['commit_sha'],'tree_sha':manifest['tree_sha'],'inventory':inventory,
                'inventory_complete':True,'targets':targets,'materialized_files':len(targets),
                'source_bytes':total,'materialized_bytes':materialized_bytes,
                'git_history_transferred_to_executor':False,'compiled':False,
                'access_method':'verified_local_checkout','duration_ms':int((time.monotonic()-start)*1000)}
            os.replace(staged,destination)
            return receipt
    finally:
        os.close(root_fd)


def persist_project_artifact(output, key, raw):
    """Create an immutable bounded artifact next to the existing receipt.

    Large generated bytes are stored once, not duplicated inside a 16 MiB
    receipt. Repeated identical writes are idempotent; corrupt existing bytes,
    symlinks and arbitrary names cannot replace an earlier artifact.
    """
    from nico.assessment_cpp_project_snapshot import PROJECT_GENERATED_STREAM_LIMIT, _stable_bytes
    if (key not in {'project-generated-context', 'project-compiler-evidence', 'project-static-evidence'} or not isinstance(raw, bytes)
            or len(raw) > PROJECT_GENERATED_STREAM_LIMIT):
        raise ValueError('qualification_artifact_invalid')
    output = Path(output).absolute()
    if output.is_symlink() or output != output.resolve(strict=True):
        raise ValueError('qualification_artifact_path_invalid')
    directory = output / 'artifacts'
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory != directory.resolve(strict=True):
        raise ValueError('qualification_artifact_path_invalid')
    sha = hashlib.sha256(raw).hexdigest()
    path = directory / (key + '-' + sha + '.json')
    if path.exists() or path.is_symlink():
        if _stable_bytes(directory, path.name, PROJECT_GENERATED_STREAM_LIMIT) != raw:
            raise ValueError('qualification_artifact_existing_mismatch')
    else:
        fd, temporary = tempfile.mkstemp(prefix='.generated-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            try:
                os.link(temporary, path)  # Exclusive publication, never overwrite.
            except FileExistsError:
                if _stable_bytes(directory, path.name, PROJECT_GENERATED_STREAM_LIMIT) != raw:
                    raise ValueError('qualification_artifact_existing_mismatch')
        finally:
            os.unlink(temporary)
    return {'path': 'artifacts/' + path.name, 'sha256': sha, 'bytes': len(raw)}


def qualify_configuration_checkout(args):
    """Prepare the next frozen execution contract using real isolated configure."""
    from nico.assessment_cpp_full_project import _json
    from nico.assessment_cpp_configuration_probe import probe_project_configuration
    args.output.mkdir(parents=True, exist_ok=True)
    evidence={'schema':'nico.cpp-configuration-qualification.v1','status':'UNPROVEN',
        'stage':'source_inventory','source':None,'probe':None,
        'production_dispatch_exercised':False,'production_qualified':False,
        'compiled':False,'tests_executed':False}
    def retain():
        data=canonical_bytes(evidence)
        if len(data)>16*1024*1024: raise ValueError('qualification_evidence_budget')
        temporary=args.output/'receipt.json.tmp'
        with temporary.open('wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary,args.output/'receipt.json')
    retain()
    try:
        with args.qualification_manifest.open('rb') as handle: raw=handle.read(16385)
        if len(raw)>16384: raise ValueError('qualification_manifest_size')
        manifest=_json(raw)
        evidence['benchmark_sha256']=hashlib.sha256(raw).hexdigest()
        execution_contract = None
        if getattr(args, 'baseline_execution_contract', None) is not None:
            raw_execution = args.baseline_execution_contract.read_bytes()
            if len(raw_execution) > 16384: raise ValueError('qualification_execution_contract_size')
            execution_contract = _json(raw_execution)
            evidence['execution_contract_sha256'] = hashlib.sha256(raw_execution).hexdigest()
        with tempfile.TemporaryDirectory(prefix='nico-project-qualification-') as temporary:
            root=Path(temporary)/'source'
            evidence['source']=freeze_configuration_checkout(args.qualification_source,root,manifest)
            evidence['stage']='source_frozen'; retain()
            unit_test_data = None
            if getattr(args, 'unit_test_data', None) is not None:
                data_root = Path(args.unit_test_data)
                if data_root.is_symlink() or not data_root.is_dir():
                    raise ValueError('qualification_unit_test_data_invalid')
                unit_test_data = {}
                for path in sorted(data_root.iterdir()):
                    if path.is_symlink() or not path.is_file() or not path.name.isascii():
                        raise ValueError('qualification_unit_test_data_invalid')
                    unit_test_data[path.name] = path.read_bytes()
                if not unit_test_data:
                    raise ValueError('qualification_unit_test_data_invalid')
            def save_probe(value):
                evidence.update(stage='isolated_baseline' if execution_contract is not None else 'isolated_configuration',
                    probe=value, compiled=value['compiled'], tests_executed=value['tests_executed']); retain()
            result=probe_project_configuration(root,evidence['source']['targets'],args.image,
                project_options=manifest['project_options'],retain=save_probe,
                baseline_execution=execution_contract, unit_test_data=unit_test_data,
                capture_generated_context=getattr(args, 'capture_generated_context', False),
                project_compiler_evidence=getattr(args, 'project_compiler_evidence', False),
                project_static_analysis=getattr(args, 'project_static_analysis', False),
                retain_artifact=lambda key, raw: persist_project_artifact(args.output, key, raw))
            evidence['status']=result['status']
            evidence.update(compiled=result['compiled'], tests_executed=result['tests_executed'])
            success = 'BASELINE_EXECUTED' if execution_contract is not None else 'CONFIGURATION_CAPTURED'
            evidence['stage']='completed' if result['status']==success else 'execution_unproven' if execution_contract is not None else 'configuration_unproven'
    except (Exception, KeyboardInterrupt) as exc:
        import re
        code=str(exc) if isinstance(exc,ValueError) else ''
        evidence['error']=(code if re.fullmatch(r'qualification_[a-z_]+',code) else 'qualification_failed')
        raise
    finally:
        retain()
        print(json.dumps({'status':evidence['status'],'stage':evidence['stage'],
                          'compiled':evidence['compiled'],'tests_executed':evidence['tests_executed'],'production_qualified':False}))
    if evidence['stage']!='completed':
        raise ValueError('qualification_configuration_unproven')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--qualification-source', type=Path, required=True)
    parser.add_argument('--qualification-manifest', type=Path, required=True)
    parser.add_argument('--baseline-execution-contract', type=Path)
    parser.add_argument('--unit-test-data', type=Path)
    parser.add_argument('--capture-generated-context', action='store_true')
    parser.add_argument('--project-compiler-evidence', action='store_true')
    parser.add_argument('--project-static-analysis', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('cpp-configuration-qualification'))
    qualify_configuration_checkout(parser.parse_args())


if __name__ == '__main__':
    main()
