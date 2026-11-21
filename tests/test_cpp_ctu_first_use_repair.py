"""Owned installer integrity controls; native semantics are tested separately."""
from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path

import pytest
from scripts import repair_cppcheck_ctu_first_use as repair

BUNDLE = Path(__file__).resolve().parents[1] / 'scripts/cppcheck-ctu-first-use'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


@pytest.fixture
def owned(tmp_path, monkeypatch):
    source, bundle = tmp_path/'source', tmp_path/'bundle'
    source.mkdir(); bundle.mkdir()
    manifest = json.loads((BUNDLE/'manifest.json').read_bytes())
    populations = {}
    for variant in sorted(repair.VARIANTS):
        version = variant.encode()
        originals = {n: b'// '+n.encode()+b'\nint shared = 0;\n// '+(b'common')+b'\n'
                     for n in repair.SOURCES}
        prerequisites = {n: b'// '+n.encode()+b' '+(version if n in {'lib/tokenize.cpp','lib/tokenlist.cpp'} else b'observer')+b'\n'
                         for n in repair.PREREQUISITES}
        results = {n: raw.replace(b'int shared = 0;', b'int shared = 1;') for n,raw in originals.items()}
        populations[variant] = (originals, prerequisites, results)
        manifest['variants'][variant]['sources'] = {n: {'before_sha256':sha(originals[n]), 'after_sha256':sha(results[n])} for n in originals}
        manifest['variants'][variant]['prerequisites'] = {n:sha(raw) for n,raw in prerequisites.items()}
    first = sorted(repair.VARIANTS)[0]
    originals, prerequisites, results = populations[first]
    patch = ''.join(f'diff --git a/{n} b/{n}\n'+''.join(difflib.unified_diff(originals[n].decode().splitlines(True), results[n].decode().splitlines(True), fromfile='a/'+n,tofile='b/'+n,n=0)) for n in sorted(originals)).encode()
    (bundle/manifest['patch']).write_bytes(patch)
    (bundle/manifest['native_controls']).write_bytes(b'// owned control\n')
    manifest['patch_sha256'] = sha(patch)
    manifest['native_controls_sha256'] = sha(b'// owned control\n')
    def pin():
        raw=json.dumps(manifest,sort_keys=True).encode();(bundle/'manifest.json').write_bytes(raw)
        monkeypatch.setattr(repair,'MANIFEST_SHA256',sha(raw))
    def install(variant=first):
        for n,raw in {**populations[variant][0],**populations[variant][1]}.items():
            p=source/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(0o640)
    pin();install()
    return source,bundle,manifest,populations,pin,install


def snapshot(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def test_real_bundle_identity_and_reviewed_descendant_outputs():
    raw=(BUNDLE/'manifest.json').read_bytes();assert sha(raw)==repair.MANIFEST_SHA256
    m=json.loads(raw)
    assert sha((BUNDLE/m['patch']).read_bytes())==m['patch_sha256']
    assert sha((BUNDLE/m['native_controls']).read_bytes())==m['native_controls_sha256']
    assert sha(Path(repair.parser.__file__).read_bytes())==repair.PARSER_SHA256
    for variant in m['variants'].values():
        assert variant['sources']=={'lib/ctu.cpp': {
            'before_sha256':'ad9b01ac6a44f5d5f4101443d550876312b12a17ab11eec332f67b3eb9a85806',
            'after_sha256':'f3e363ae33cb8489ff25f4c1ab7ca02adbf0ee9f5fe1f7d463669e1eaa259ada'}}
    index=json.loads((BUNDLE.parent/'cppcheck-replacement-index/manifest.json').read_bytes())
    for name,entry in m['variants'].items():
        for source,pair in index['variants'][name]['sources'].items():
            assert entry['prerequisites'][source]==pair['after_sha256']
        assert entry['expected_prior_repairs']['repair_cppcheck_replacement_index.py']==sha((BUNDLE.parent/'repair_cppcheck_replacement_index.py').read_bytes())



@pytest.mark.parametrize('variant',sorted(repair.VARIANTS))
def test_complete_variant_receipt_preserves_prerequisites_mode_and_rejects_reapply(owned,variant):
    source,bundle,m,populations,pin,install=owned;install(variant)
    receipt=repair.apply_repair(source,bundle)
    assert receipt['variant']==variant and receipt['sources']==m['variants'][variant]['sources']
    assert receipt['native_qualification_completed'] is False
    assert receipt['application_script_sha256']==sha(Path(repair.__file__).read_bytes())
    assert receipt['patch_parser_sha256']==repair.PARSER_SHA256
    assert receipt['manifest_sha256']==repair.MANIFEST_SHA256
    assert snapshot(source)=={**populations[variant][2],**populations[variant][1]}
    assert all((source/n).stat().st_mode&0o777==0o640 for n in repair.SOURCES)
    before=snapshot(source)
    with pytest.raises(ValueError,match='source_variant_mismatch'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


@pytest.mark.parametrize('member',sorted(repair.SOURCES|repair.PREREQUISITES))
def test_changed_any_member_rejected_before_any_writes(owned,member):
    source,bundle,*_=owned;(source/member).write_bytes(b'changed\n');before=snapshot(source)
    with pytest.raises(ValueError,match='source_variant_mismatch'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_mixed_valid_variant_files_rejected(owned):
    source,bundle,m,populations,pin,install=owned
    variants=sorted(repair.VARIANTS);(source/'lib/tokenize.cpp').write_bytes(populations[variants[1]][1]['lib/tokenize.cpp'])
    before=snapshot(source)
    with pytest.raises(ValueError,match='source_variant_mismatch'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


@pytest.mark.parametrize('target',['source-file','source-directory','source-root','bundle-root','manifest','patch','control'])
def test_symlink_paths_rejected(owned,tmp_path,target):
    source,bundle,*_=owned
    path={'source-file':source/'lib/ctu.cpp','source-directory':source/'lib','source-root':source,
          'bundle-root':bundle,'manifest':bundle/'manifest.json','patch':bundle/'ctu-first-use-v1.patch','control':bundle/'native-controls.cpp'}[target]
    moved=tmp_path/'moved';path.rename(moved);path.symlink_to(moved,target_is_directory=moved.is_dir())
    with pytest.raises((ValueError,OSError)):repair.apply_repair(source,bundle)


@pytest.mark.parametrize('member',['manifest.json','ctu-first-use-v1.patch','native-controls.cpp'])
def test_bundle_tampering_rejected(owned,member):
    source,bundle,*_=owned;before=snapshot(source);p=bundle/member;p.write_bytes(p.read_bytes()+b'changed')
    with pytest.raises(ValueError):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


@pytest.mark.parametrize('field,value',[('patch','../outside.patch'),('native_controls','/outside.cpp'),('schema','wrong')])
def test_even_repinned_manifest_path_or_schema_rejected(owned,field,value):
    source,bundle,m,populations,pin,install=owned;m[field]=value;pin();before=snapshot(source)
    with pytest.raises(ValueError,match='manifest_invalid'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_wrong_output_digest_is_not_accepted(owned):
    source,bundle,m,populations,pin,install=owned
    for v in m['variants'].values():v['sources']['lib/ctu.cpp']['after_sha256']='0'*64
    pin();before=snapshot(source)
    with pytest.raises(ValueError,match='output_mismatch'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_invalid_patch_population_or_context_rejected(owned):
    source,bundle,m,populations,pin,install=owned
    patch=b'diff --git a/outside b/outside\n--- a/outside\n+++ b/outside\n'
    (bundle/m['patch']).write_bytes(patch);m['patch_sha256']=sha(patch);pin();before=snapshot(source)
    with pytest.raises(ValueError,match='patch_invalid'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_source_change_while_staging_rejected_without_overwrite(owned,monkeypatch):
    source,bundle,*_=owned;stage=repair._stage;changed=False
    def racing(*args):
        nonlocal changed
        result=stage(*args)
        if not changed:(source/'lib/ctu.cpp').write_bytes(b'concurrent\n');changed=True
        return result
    monkeypatch.setattr(repair,'_stage',racing)
    with pytest.raises(ValueError,match='source_changed'):repair.apply_repair(source,bundle)
    assert (source/'lib/ctu.cpp').read_bytes()==b'concurrent\n'
    assert not list(source.rglob('.nico-ctu-*'))


def test_failed_replace_preserves_source(owned,monkeypatch):
    source,bundle,*_=owned;before=snapshot(source);replace=repair.os.replace;calls=0
    def failing(*args):
        nonlocal calls
        calls+=1
        if calls==1:raise OSError('owned injected replace failure')
        return replace(*args)
    monkeypatch.setattr(repair.os,'replace',failing)
    with pytest.raises(OSError,match='injected'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before
    assert not list(source.rglob('.nico-ctu-*'))


def test_parser_identity_mismatch_rejected(owned,monkeypatch):
    source,bundle,*_=owned;monkeypatch.setattr(repair,'PARSER_SHA256','0'*64)
    with pytest.raises(ValueError,match='manifest_invalid'):repair.apply_repair(source,bundle)


@pytest.mark.parametrize('content',[b'',b'x'*(repair.LIMIT+1)])
def test_empty_or_oversized_source_rejected(owned,content):
    source,bundle,*_=owned;(source/'lib/ctu.cpp').write_bytes(content);before=snapshot(source)
    with pytest.raises(ValueError,match='source_invalid'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_staging_failure_preserves_all_original_sources(owned,monkeypatch):
    source,bundle,*_=owned;before=snapshot(source);stage=repair._stage;calls=0
    def fail(*args):
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('owned staging failure')
        return stage(*args)
    monkeypatch.setattr(repair,'_stage',fail)
    with pytest.raises(OSError,match='staging failure'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before
    assert not list(source.rglob('.nico-ctu-*'))


def test_changed_parser_bytes_rejected_before_mutation(owned,monkeypatch):
    source,bundle,*_=owned;before=snapshot(source);stable=repair.parser.stable
    def altered(path,*args):
        raw,mode=stable(path,*args)
        return (raw+b'changed',mode) if Path(path)==Path(repair.parser.__file__) else (raw,mode)
    monkeypatch.setattr(repair.parser,'stable',altered)
    with pytest.raises(ValueError,match='parser_mismatch'):repair.apply_repair(source,bundle)
    assert snapshot(source)==before


def test_readonly_change_during_commit_rolls_back_owned_files(owned,monkeypatch):
    source,bundle,*_=owned;before=snapshot(source);replace=repair.os.replace;changed=False
    def race(*args):
        nonlocal changed
        result=replace(*args)
        if not changed:(source/'lib/tokenize.cpp').write_bytes(b'concurrent readonly change\n');changed=True
        return result
    monkeypatch.setattr(repair.os,'replace',race)
    with pytest.raises(ValueError,match='output_changed'):repair.apply_repair(source,bundle)
    before['lib/tokenize.cpp']=b'concurrent readonly change\n'
    assert snapshot(source)==before
    assert not list(source.rglob('.nico-ctu-*'))
