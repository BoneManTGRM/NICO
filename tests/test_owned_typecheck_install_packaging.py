"""Build-only fixtures; never reach a cloud service or run target scripts."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import subprocess

import pytest

TOOL = Path(__file__).resolve().parents[1]/'tools/owned-typecheck-install'
spec = spec_from_file_location('package_owned_typecheck', TOOL/'package_owned_typecheck.py')
pack = module_from_spec(spec)
spec.loader.exec_module(pack)


def write(root,path,bytes_):
    target=root/path
    target.parent.mkdir(exist_ok=True,parents=True)
    target.write_bytes(bytes_)
    return target


@pytest.fixture
def build_inputs(tmp_path, monkeypatch):
    root=tmp_path/'reference'; root.mkdir()
    scripts=tmp_path/'scripts'; scripts.mkdir()
    node=write(tmp_path,'fake-fixture-node',b'owned fixture; not executable')
    src={pack.WEB+'package-lock.json':b'{}',pack.WEB+'page.ts':b'export {};'}
    deps={pack.DEPS+'fixture/data.d.ts':b'',pack.DEPS+'fixture/package.json':b'{}'}
    gen={pack.WEB+'.next/types/'+name:b'export {};' for name in pack.sealer.NAMES}
    gen[pack.WEB+'.next/package.json']=b'{"type": "commonjs"}'
    lib={'lib/lib.es2017.d.ts':b'export {};','lib/typescript.js':b'trusted TS fixture',
         'package.json':b'{"version": "6.0.3"}'}
    for p,x in (src|deps|gen|{pack.DEPS+'typescript/'+k:v for k,v in lib.items()}).items():
        write(root,p,x)
    for p in (pack.DRIVER,pack.HOST):
        write(scripts,p,b'owned fixture wrapper')
    refs={p:pack.digest(x) for p,x in (src|deps|gen|{'@compiler/'+k:v for k,v in lib.items()}).items()}
    known={
        'source_sha':pack.sealer.HISTORICAL_COMMIT,
        'compiler':{
            'node_version':'v24.22.3','node_sha256':pack.digest(node.read_bytes()),
            'version':'6.0.3','entry_sha256':refs[pack.TS_LIB+'typescript.js'],
            'package_sha256':refs['@compiler/package.json']},
        'source_inventory':{p:refs[p] for p in src},
        'generated_inputs':{p:refs[p] for p in gen},
        'read_inputs':refs,
    }
    monkeypatch.setattr(pack,'_baseline',lambda p:(b'fixture verified by fixture authority',known))
    monkeypatch.setattr(pack,'SRC_COUNT',len(src))
    monkeypatch.setattr(pack,'DEP_COUNT',len(deps))
    monkeypatch.setattr(pack,'LIB_COUNT',1)
    return dict(reference=root,baseline=tmp_path/'fixture.gz',scripts=scripts,node=node,
                producer='b'*40,out=tmp_path/'installed'),known,src,deps,gen


def test_package_matches_scanner_interface(build_inputs):
    args,known,src,deps,gen = build_inputs
    manifest=pack.publish(**args)
    out=args['out']
    assert manifest == json.loads((out/'manifest.json').read_bytes())
    assert manifest['schema']=='nico.owned-typescript-install.v1'
    assert manifest['producer_commit']==args['producer']
    assert manifest['target_commit']==pack.sealer.HISTORICAL_COMMIT
    assert manifest['target_tree']==pack.sealer.HISTORICAL_TREE
    assert manifest['generated_bundle_sha256']==pack.digest((out/'generated.zip').read_bytes())
    assert manifest['mount_digests']['source']==pack._mount_digest_bytes({p.removeprefix(pack.WEB):b for p,b in src.items()})
    assert (out/'dependencies/fixture/data.d.ts').read_bytes()==b''
    assert not (out/'apps/web/page.ts').exists()
    assert (out/'node').stat().st_mode & 0o777 == 0o555
    for file in out.rglob('*'):
        if file.is_file() and file.name!='node':
            assert file.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize('damage',['source','dependency','generated','metadata','node','path','extra_read','invalid_sha'])
def test_missing_or_changed_input_never_leaves_ready_install(build_inputs, damage):
    args, known, src, deps, gen = build_inputs
    root=args['reference']
    if damage=='source': write(root,pack.WEB+'page.ts',b'bad')
    elif damage=='dependency': (root/(pack.DEPS+'fixture/data.d.ts')).unlink()
    elif damage=='generated': write(root,pack.WEB+'.next/types/validator.ts',b'bad')
    elif damage=='metadata': write(root,pack.WEB+'.next/package.json',b'{}')
    elif damage=='node': args['node'].write_bytes(b'wrong')
    elif damage=='path':
        x=root/(pack.DEPS+'fixture/data.d.ts'); x.unlink()
        x.symlink_to(args['node'])
    elif damage=='extra_read': known['read_inputs']['outside.txt']='4'*64
    elif damage=='invalid_sha': args['producer']='0'*40
    with pytest.raises((OSError,ValueError)):
        pack.publish(**args)
    assert not args['out'].exists()


def test_vanilla_build_leaves_explicit_no_install(tmp_path):
    out=tmp_path/'empty-install'
    args=['sh',TOOL/'build_inputs.sh','does-not-exist','not-read','not-read',out,'']
    result=subprocess.run(args,capture_output=True,check=True,text=True)
    assert 'not packaged: no Railway build SHA' in result.stdout
    assert not list(out.iterdir())


def test_actual_packaged_fingerprint_manifest_is_canonical():
    zipped,known=pack._baseline(TOOL/'historical_typescript_inputs.json.gz')
    assert len(known['read_inputs'])==785
    assert known['compiler']['version']=='6.0.3'
    assert len(known['generated_inputs'])==5
