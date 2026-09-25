"""Source-bound runtime qualification plan for configure-first C/C++ execution."""
from __future__ import annotations

import ast
import base64
from copy import deepcopy
import hashlib
from pathlib import Path, PurePosixPath
import re

QA_ASSETS_COMMIT = 'cf4ec4a6b7fe814dc3f2ddbaa00cd1a7d7c7ae2f'
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
            or scope.get('fuzz_policy')!='source-declared-libfuzzer-v1'):
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
        'schema':'nico.cpp-runtime-plan.v1',
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
