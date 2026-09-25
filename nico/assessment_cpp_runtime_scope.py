"""Source-bound runtime qualification plan for configure-first C/C++ execution."""
from __future__ import annotations

import ast
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import time

QA_ASSETS_COMMIT = 'cf4ec4a6b7fe814dc3f2ddbaa00cd1a7d7c7ae2f'
UNIT_TEST_DATA_COMMIT = 'b33d85102d169b54d966ea315ad81a636680aefa'
UNIT_TEST_DATA_ASSET = {
    'policy':'source-declared-pinned-public-asset-v1',
    'repository':'bitcoin-core/qa-assets','commit_sha':UNIT_TEST_DATA_COMMIT,
    'path':'unit_test_data/script_assets_test.json',
    'git_blob_sha':'6a69755a5e53f4212f265374e14f590dcbf86496',
    'name':'script_assets_test.json',
    'url':'https://raw.githubusercontent.com/bitcoin-core/qa-assets/'+UNIT_TEST_DATA_COMMIT+'/unit_test_data/script_assets_test.json',
    'sha256':'cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095',
    'bytes':9243520,
}
_RUNTIME_INTERFACES = (
    'CMakeLists.txt','test/functional/test_runner.py','test/fuzz/test_runner.py',
    'src/test/fuzz/CMakeLists.txt','src/test/fuzz/connect_block.cpp',
)
_OPTIONAL_UNIT_INTERFACE = 'src/test/script_assets_tests.cpp'
_CORPUS = (
    {
        'path':'fuzz_corpora/connect_block/00e43b08640114362c899209ab336025af5c7432',
        'git_blob_sha':'b73d1c472076e207ada6abf0bf11e614169432df',
        'sha256':'b711ed78d4987553c5a9fe7ca143ea017af39215f87e6c222b0796779edb3b44',
        'bytes':3,'base64':'Lgo5',
    },
    {
        'path':'fuzz_corpora/connect_block/067d5096f219c64b53bb1c7d5e3754285b565a47',
        'git_blob_sha':'2725bca0006db42c8ee38c15dfa290bbe57f9a94',
        'sha256':'e7cf46a078fed4fafd0b5e3aff144802b853f8ae459a4f0c14add3314b7cc3a6',
        'bytes':1,'base64':'Cw==',
    },
)


def _safe_path(path: str) -> bool:
    return (isinstance(path,str) and 0 < len(path) <= 1000 and not PurePosixPath(path).is_absolute()
        and PurePosixPath(path).as_posix() == path and ':' not in path and '\\' not in path
        and all(part not in {'','.','..','.git'} for part in path.split('/')))


def _read_exact(source: Path, targets: dict[str,str], path: str, limit: int = 2*1024*1024) -> bytes:
    if not _safe_path(path) or path not in targets:
        raise ValueError('worker_runtime_scope_unsupported')
    root=Path(source)
    file=root/path
    if root.is_symlink() or not root.is_dir() or file.is_symlink() or not file.is_file():
        raise ValueError('worker_runtime_scope_unsupported')
    raw=file.read_bytes()
    if not raw or len(raw)>limit or hashlib.sha256(raw).hexdigest()!=targets[path]:
        raise ValueError('worker_runtime_scope_unsupported')
    return raw


def _base_scripts(raw: bytes) -> list[str]:
    try:
        tree=ast.parse(raw.decode('utf-8'))
    except (UnicodeDecodeError,SyntaxError) as exc:
        raise ValueError('worker_runtime_scope_unsupported') from exc
    values=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BASE_SCRIPTS' for t in node.targets):
            values=node.value
            break
    if not isinstance(values,(ast.List,ast.Tuple)):
        raise ValueError('worker_runtime_scope_unsupported')
    rows=[item.value for item in values.elts if isinstance(item,ast.Constant) and isinstance(item.value,str)]
    if not rows or len(rows)>1000:
        raise ValueError('worker_runtime_scope_unsupported')
    return rows


def _select_functional_tests(rows: list[str], project_options: dict[str,str], targets: dict[str,str]) -> list[str]:
    prefixes=['feature_','mempool_','p2p_','rpc_']
    if project_options.get('ENABLE_WALLET')=='ON': prefixes.append('wallet_')
    selected=[]
    for prefix in prefixes:
        choices=[row for row in rows if row.startswith(prefix)]
        if not choices:
            raise ValueError('worker_runtime_scope_unsupported')
        selected.append(choices[-1])
    if project_options.get('ENABLE_IPC')=='ON':
        choices=[row for row in rows if row.split()[0]=='interface_ipc.py']
        if not choices:
            raise ValueError('worker_runtime_scope_unsupported')
        selected.append(choices[-1])
    for row in selected:
        script=row.split()[0]
        if 'test/functional/'+script not in targets:
            raise ValueError('worker_runtime_scope_unsupported')
    return selected


def derive_runtime_plan(source, targets, project_options, scope):
    if (not isinstance(targets,dict) or not targets or not isinstance(project_options,dict)
            or not isinstance(scope,dict) or scope.get('schema')!='nico.cpp-runtime-scope.v1'
            or scope.get('functional_policy')!='source-declared-functional-v1'
            or scope.get('fuzz_policy')!='source-declared-libfuzzer-v1'
            or scope.get('total_seconds')!=6000):
        raise ValueError('worker_runtime_scope_unsupported')
    for path,digest in targets.items():
        if not _safe_path(path) or not isinstance(digest,str) or re.fullmatch(r'[0-9a-f]{64}',digest) is None:
            raise ValueError('worker_runtime_scope_unsupported')
    root=Path(source)
    cmake=_read_exact(root,targets,'CMakeLists.txt')
    functional_raw=_read_exact(root,targets,'test/functional/test_runner.py')
    fuzz_runner=_read_exact(root,targets,'test/fuzz/test_runner.py')
    fuzz_cmake=_read_exact(root,targets,'src/test/fuzz/CMakeLists.txt')
    _read_exact(root,targets,'src/test/fuzz/connect_block.cpp')
    unit_data=None
    if _OPTIONAL_UNIT_INTERFACE in targets:
        unit_source=_read_exact(root,targets,_OPTIONAL_UNIT_INTERFACE,4*1024*1024)
        if b'DIR_UNIT_TEST_DATA' in unit_source and b'script_assets_test.json' in unit_source:
            unit_data=deepcopy(UNIT_TEST_DATA_ASSET)
    text=cmake.decode('utf-8',errors='strict')
    if ('SANITIZERS' not in text or 'BUILD_FUZZ_BINARY' not in text or 'BUILD_FOR_FUZZING' not in text
            or b'add_executable(fuzz' not in fuzz_cmake or b'connect_block.cpp' not in fuzz_cmake
            or b'FUZZ' not in fuzz_runner):
        raise ValueError('worker_runtime_scope_unsupported')
    selected=_select_functional_tests(_base_scripts(functional_raw),project_options,targets)
    corpus=[]
    for row in _CORPUS:
        raw=base64.b64decode(row['base64'],validate=True)
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError('worker_runtime_scope_asset_invalid')
        corpus.append(deepcopy(row))
    return {
        'schema':'nico.cpp-runtime-plan.v1','total_seconds':scope['total_seconds'],
        'unit_test_data':unit_data,
        'functional':{
            'policy':scope['functional_policy'],'runner':'test/functional/test_runner.py',
            'selected_tests':selected,'seconds':scope['functional_seconds'],'parallel':scope['parallel'],
        },
        'sanitizers':{
            'interface':'SANITIZERS','kinds':list(scope['sanitizers']),
            'build_seconds':scope['sanitizer_build_seconds'],'test_seconds':scope['sanitizer_test_seconds'],
            'test_case_seconds':scope['sanitizer_test_case_seconds'],'parallel':scope['parallel'],
        },
        'fuzz':{
            'policy':scope['fuzz_policy'],'build_target':'fuzz','binary':'bin/fuzz','target':'connect_block',
            'qa_assets_repository':'bitcoin-core/qa-assets','qa_assets_commit':QA_ASSETS_COMMIT,
            'corpus':corpus,'replay_runs':scope['fuzz_replay_runs'],'campaign_runs':scope['fuzz_campaign_runs'],
            'campaign_seconds':scope['fuzz_campaign_seconds'],'parallel':1,
        },
    }


def capture_runtime_interfaces(source, targets):
    if not isinstance(targets,dict) or not targets:
        raise ValueError('worker_runtime_scope_interfaces_invalid')
    paths=list(_RUNTIME_INTERFACES)
    if _OPTIONAL_UNIT_INTERFACE in targets:
        paths.append(_OPTIONAL_UNIT_INTERFACE)
    result={}
    for path in paths:
        raw=_read_exact(Path(source),targets,path,4*1024*1024)
        result[path]={'sha256':targets[path],'bytes':len(raw),'base64':base64.b64encode(raw).decode()}
    return result


def derive_runtime_plan_from_interfaces(interfaces, targets, project_options, scope):
    expected=set(_RUNTIME_INTERFACES)
    if _OPTIONAL_UNIT_INTERFACE in targets:
        expected.add(_OPTIONAL_UNIT_INTERFACE)
    if not isinstance(interfaces,dict) or set(interfaces)!=expected:
        raise ValueError('worker_runtime_scope_interfaces_invalid')
    with tempfile.TemporaryDirectory(prefix='nico-runtime-interfaces-') as temporary:
        root=Path(temporary)
        for path in sorted(expected):
            row=interfaces[path]
            if (not isinstance(row,dict) or set(row)!={'sha256','bytes','base64'}
                    or row.get('sha256')!=targets.get(path) or type(row.get('bytes')) is not int
                    or not 1<=row['bytes']<=4*1024*1024):
                raise ValueError('worker_runtime_scope_interfaces_invalid')
            try:
                raw=base64.b64decode(row['base64'],validate=True)
            except (ValueError,TypeError) as exc:
                raise ValueError('worker_runtime_scope_interfaces_invalid') from exc
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
                raise ValueError('worker_runtime_scope_interfaces_invalid')
            output=root/path; output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(raw)
        return derive_runtime_plan(root,targets,project_options,scope)


def acquire_unit_test_data(plan, checkpoint, *, download=None):
    asset=(plan or {}).get('unit_test_data') if isinstance(plan,dict) else None
    if asset is None:
        return None
    if asset!=UNIT_TEST_DATA_ASSET or not callable(checkpoint):
        raise ValueError('worker_runtime_scope_asset_invalid')
    if download is None:
        from nico.assessment_worker_source import download_public
        download=download_public
    with tempfile.TemporaryDirectory(prefix='nico-runtime-asset-') as temporary:
        path=Path(temporary)/asset['name']
        download(asset['url'],path,limit=asset['bytes'],checkpoint=checkpoint,deadline=time.monotonic()+30)
        if path.is_symlink() or not path.is_file():
            raise ValueError('worker_runtime_scope_asset_invalid')
        raw=path.read_bytes()
    if len(raw)!=asset['bytes'] or hashlib.sha256(raw).hexdigest()!=asset['sha256']:
        raise ValueError('worker_runtime_scope_asset_invalid')
    return {asset['name']:raw}


def retained_runtime_bytes(interfaces, plan, evidence):
    return json.dumps({'schema':'nico.cpp-runtime-retained.v1','interfaces':interfaces,
        'plan':plan,'evidence':evidence},sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def validate_retained_runtime(raw, targets, project_options, scope):
    from nico.assessment_cpp_full_project import _json
    from nico.assessment_cpp_runtime_execution import validate_runtime_evidence
    if not isinstance(raw,bytes) or not 0<len(raw)<=64*1024*1024:
        raise ValueError('worker_runtime_retained_invalid')
    value=_json(raw)
    if (not isinstance(value,dict) or set(value)!={'schema','interfaces','plan','evidence'}
            or value.get('schema')!='nico.cpp-runtime-retained.v1'):
        raise ValueError('worker_runtime_retained_invalid')
    plan=derive_runtime_plan_from_interfaces(value['interfaces'],targets,project_options,scope)
    if value['plan']!=plan:
        raise ValueError('worker_runtime_retained_invalid')
    summary=validate_runtime_evidence(value['evidence'],plan,project_options=project_options)
    return {'plan':plan,'summary':summary,'native_evidence_sha256':hashlib.sha256(raw).hexdigest(),
        'duration_ms':value['evidence']['duration_ms']}
