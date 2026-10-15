"""All packages, signatures and generated declarations below are owned fixtures."""
import base64
from copy import deepcopy
import gzip
import hashlib
import io
import json
import tarfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def sha(raw): return hashlib.sha256(raw).hexdigest()
def wire(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def digest(value): return sha(wire(value))


def archive(files, *, symlink=False):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, raw in files.items():
            entry = tarfile.TarInfo('package/'+name); entry.size = len(raw)
            if symlink and name=='index.d.ts':
                entry.type=tarfile.SYMTYPE; entry.linkname='/outside'; entry.size=0
                tar.addfile(entry)
            else: tar.addfile(entry, io.BytesIO(raw))
    return gzip.compress(out.getvalue(), mtime=0)


@pytest.fixture
def sample():
    from nico.typescript_offline_bundle_v1 import BundlePolicy
    private = Ed25519PrivateKey.generate()
    package_files = {'package.json':b'{"name":"owned-tool","version":"1.0.0"}',
                     'index.d.ts':b'export declare const n: number;', 'generator.js':b'// owned inert generator identity'}
    packed = archive(package_files)
    integrity = 'sha512-'+base64.b64encode(hashlib.sha512(packed).digest()).decode()
    root_package = {'name':'owned-app','dependencies':{'owned-tool':'1.0.0'}}
    lock = {'lockfileVersion':3,'packages':{'':root_package, 'node_modules/owned-tool':
        {'version':'1.0.0','resolved':'https://registry.npmjs.org/owned-tool/-/owned-tool-1.0.0.tgz','integrity':integrity}}}
    source = {'package.json':wire(root_package),'package-lock.json':wire(lock), 'tsconfig.json':b'{"compilerOptions":{"noEmit":true}}', 'src/main.ts':b'export const n=1;'}
    generated = {'.next/types/routes.d.ts':b'export type Route = "/";'}
    identity = {'repository':'owned/app','commit_sha':'a'*40,'tree_sha':'b'*40,'run_id':'owned_run','snapshot_id':'owned_snapshot'}
    compiler = {'version':'6.0.3','package_sha256':'1'*64,'compiler_sha256':'2'*64,'libraries_sha256':'3'*64,'node_sha256':'4'*64}
    build = {'provider':'github-actions','repository':'owned/app','workflow_path':'.github/workflows/owned.yml',
             'workflow_sha':'c'*40,'run_id':'123','attempt':1,'conclusion':'success'}
    generator = {'package_path':'node_modules/owned-tool','version':'1.0.0','entry_path':'generator.js',
                 'entry_sha256':sha(package_files['generator.js']),'config_path':'tsconfig.json','config_sha256':sha(source['tsconfig.json'])}
    package_inventory = {'node_modules/owned-tool':{'archive_sha256':sha(packed), 'integrity':integrity,
        'files':{name:sha(raw) for name,raw in package_files.items()}}}
    statement = {'schema':'nico.typescript.offline-provenance.v1','source':identity,'compiler':compiler,'build':build,'generator':generator,
        'lockfile':{'path':'package-lock.json','sha256':sha(source['package-lock.json'])},
        'source_inventory_sha256':digest({p:sha(b) for p,b in source.items()}),
        'package_inventory_sha256':digest(package_inventory),'generated_inventory_sha256':digest({p:sha(b) for p,b in generated.items()}),
        'package_inventory_complete':True,'generated_inventory_complete':True}
    envelope = {'key_id':'owned-controller','statement':statement,'signature':base64.b64encode(private.sign(wire(statement))).decode()}
    policy = BundlePolicy(identity, compiler, build, generator, {p:sha(b) for p,b in source.items()},
        frozenset(generated), 'owned-controller', private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    return {'source_files':source, 'packages':{'node_modules/owned-tool':packed}, 'generated_files':generated,
            'envelope':envelope, 'policy':policy, 'compiler_identity':compiler}, private, package_files


def verify(data):
    from nico.typescript_offline_bundle_v1 import verify_offline_bundle
    return verify_offline_bundle(**data)


def resign(data, private):
    data['envelope']['signature'] = base64.b64encode(private.sign(wire(data['envelope']['statement']))).decode()


def test_owned_bundle_verifies_without_qualification(sample):
    data, _, _ = sample
    before = deepcopy(data['source_files'])
    result = verify(data)
    assert result['verified'] is True
    assert result['qualified_for_production'] is False
    assert result['os_isolation_verified'] is False
    assert result['source'] == data['policy'].source
    assert result['package_count'] == 1 and result['generated_count'] == 1
    assert data['source_files'] == before


@pytest.mark.parametrize('field', ['source','compiler','build','generator'])
def test_signed_but_wrong_authority_binding_rejected(sample, field):
    data, private, _ = sample
    data['envelope']['statement'][field] = {'wrong':'identity'}; resign(data, private)
    with pytest.raises(ValueError): verify(data)


@pytest.mark.parametrize('field', ['source_inventory_sha256','package_inventory_sha256','generated_inventory_sha256'])
def test_signed_but_wrong_inventory_rejected(sample, field):
    data, private, _ = sample
    data['envelope']['statement'][field] = '0'*64; resign(data, private)
    with pytest.raises(ValueError): verify(data)


@pytest.mark.parametrize('field', ['package_inventory_complete','generated_inventory_complete'])
def test_incomplete_attestation_rejected(sample, field):
    data, private, _ = sample
    data['envelope']['statement'][field] = False; resign(data, private)
    with pytest.raises(ValueError): verify(data)


def test_signature_key_and_actual_compiler_rejected(sample):
    data, _, _ = sample
    bad = deepcopy(data); bad['envelope']['signature'] = base64.b64encode(b'0'*64).decode()
    with pytest.raises(ValueError): verify(bad)
    bad = deepcopy(data); bad['envelope']['key_id'] = 'target-supplied-key'
    with pytest.raises(ValueError): verify(bad)
    bad = deepcopy(data); bad['compiler_identity']['compiler_sha256'] = '0'*64
    with pytest.raises(ValueError): verify(bad)


def test_package_integrity_and_completeness(sample):
    data, _, _ = sample
    bad = deepcopy(data); bad['packages']['node_modules/owned-tool'] += b'tamper'
    with pytest.raises(ValueError): verify(bad)
    bad = deepcopy(data); bad['packages'] = {}
    with pytest.raises(ValueError): verify(bad)
    bad = deepcopy(data); bad['packages']['node_modules/extra'] = b''
    with pytest.raises(ValueError): verify(bad)


def test_source_and_generated_tampering(sample):
    data, _, _ = sample
    for field, key in [('source_files','src/main.ts'),('generated_files','.next/types/routes.d.ts')]:
        bad = deepcopy(data); bad[field][key] += b'changed'
        with pytest.raises(ValueError): verify(bad)
    bad = deepcopy(data); bad['generated_files'] = {}
    with pytest.raises(ValueError): verify(bad)


@pytest.mark.parametrize('name', ['../escape','/outside','nested/../../outside','node_modules/evil'])
def test_generated_path_escape_rejected(sample, name):
    data, _, _ = sample; data['generated_files'][name] = b'owned'
    with pytest.raises(ValueError): verify(data)


def test_archive_parser_rejects_symlinks_and_traversal(sample):
    from nico.typescript_offline_bundle_v1 import _archive_inventory
    _, _, files = sample
    with pytest.raises(ValueError): _archive_inventory(archive(files, symlink=True))
    with pytest.raises(ValueError): _archive_inventory(archive({'../outside':b'owned'}))


def test_archive_parser_rejects_duplicate_and_oversize():
    from nico.typescript_offline_bundle_v1 import _archive_inventory
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as tar:
        for _ in range(2):
            entry=tarfile.TarInfo('package/a'); entry.size=1; tar.addfile(entry,io.BytesIO(b'x'))
    with pytest.raises(ValueError): _archive_inventory(gzip.compress(out.getvalue()))
    with pytest.raises(ValueError): _archive_inventory(b'x'*(8*1024*1024+1))


def rebind_source(data, private):
    from dataclasses import replace
    inventory={p:sha(raw) for p,raw in data['source_files'].items()}
    data['policy']=replace(data['policy'],source_inventory=inventory)
    s=data['envelope']['statement']; s['source_inventory_sha256']=digest(inventory)
    s['lockfile']['sha256']=inventory['package-lock.json']; resign(data,private)


@pytest.mark.parametrize('change', [
    ('lockfileVersion',3.0), ('optional',True), ('link',True), ('peerDependencies',{'missing':'1.0.0'}),
    ('optionalDependencies',{'missing':'1.0.0'}), ('os',['different']), ('resolved','file:owned.tgz'),
    ('version','2.0.0'), ('integrity','sha512-invalid'),
])
def test_unsupported_or_conflicting_lock_semantics(sample,change):
    data,private,_=sample; field,value=change; lock=json.loads(data['source_files']['package-lock.json'])
    if field=='lockfileVersion': lock[field]=value
    else: lock['packages']['node_modules/owned-tool'][field]=value
    data['source_files']['package-lock.json']=wire(lock); rebind_source(data,private)
    with pytest.raises(ValueError): verify(data)


def test_root_dependency_graph_missing_or_range_is_rejected(sample):
    data,private,_=sample
    for dependencies in ({'missing':'1.0.0'},{'owned-tool':'^1.0.0'}):
        bad=deepcopy(data); lock=json.loads(bad['source_files']['package-lock.json']); package=json.loads(bad['source_files']['package.json'])
        lock['packages']['']['dependencies']=dependencies; package['dependencies']=dependencies
        bad['source_files']['package-lock.json']=wire(lock); bad['source_files']['package.json']=wire(package)
        rebind_source(bad,private)
        with pytest.raises(ValueError): verify(bad)


@pytest.mark.parametrize('raw',[b'{"lockfileVersion":3,"lockfileVersion":3}', b'{"name":"a","name":"b"}',b'\xff'])
def test_duplicate_or_invalid_metadata_json_rejected(raw):
    from nico.typescript_offline_bundle_v1 import _json
    with pytest.raises(ValueError): _json(raw)


@pytest.mark.parametrize('kind',[tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE])
def test_archive_special_members_rejected(kind):
    from nico.typescript_offline_bundle_v1 import _archive_inventory
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as tar:
        entry=tarfile.TarInfo('package/special'); entry.type=kind; entry.linkname='package/other'; tar.addfile(entry)
    with pytest.raises(ValueError): _archive_inventory(gzip.compress(out.getvalue()))


@pytest.mark.parametrize('fmt',[tarfile.PAX_FORMAT,tarfile.GNU_FORMAT])
def test_extended_archive_metadata_rejected(fmt):
    from nico.typescript_offline_bundle_v1 import _archive_inventory
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=fmt) as tar:
        entry=tarfile.TarInfo('package/'+'x'*160); entry.size=1; tar.addfile(entry,io.BytesIO(b'x'))
    with pytest.raises(ValueError): _archive_inventory(gzip.compress(out.getvalue()))


def test_bounded_gzip_expansion_and_member_count(monkeypatch):
    from nico import typescript_offline_bundle_v1 as module
    monkeypatch.setattr(module,'MAX_UNPACKED',1024)
    with pytest.raises(ValueError,match='unpacked_budget'): module._archive_inventory(gzip.compress(b'x'*4096))
    monkeypatch.setattr(module,'MAX_UNPACKED',32*1024*1024)
    monkeypatch.setattr(module,'MAX_FILES',1)
    with pytest.raises(ValueError,match='entry_budget'): module._archive_inventory(archive({'one':b'x','two':b'y'}))


def test_extra_generated_or_conflicting_source_not_silently_accepted(sample):
    data,private,_=sample
    data['generated_files']['.next/types/extra.d.ts']=b'export type X=1;'
    with pytest.raises(ValueError): verify(data)
    data['envelope']['statement']['generated_inventory_sha256']=digest({p:sha(b) for p,b in data['generated_files'].items()}); resign(data,private)
    assert verify(data)['generated_count']==2  # Trusted signed complete inventory; required routes still present.
    data['source_files']['.next/types/routes.d.ts']=data['generated_files']['.next/types/routes.d.ts']; rebind_source(data,private)
    with pytest.raises(ValueError): verify(data)


def test_source_dependency_namespace_conflict_rejected(sample):
    data,private,_=sample
    data['source_files']['node_modules/owned-tool/index.d.ts']=b'conflicting owned declaration'
    rebind_source(data,private)
    with pytest.raises(ValueError,match='namespace_conflict'): verify(data)


def test_libc_install_semantics_rejected(sample):
    data,private,_=sample; lock=json.loads(data['source_files']['package-lock.json'])
    lock['packages']['node_modules/owned-tool']['libc']=['musl']
    data['source_files']['package-lock.json']=wire(lock); rebind_source(data,private)
    with pytest.raises(ValueError,match='install_semantics'): verify(data)


def test_generated_scope_and_encoding_rejected_even_when_signed(sample):
    data,private,_=sample
    for name,raw in [('evil.next/types/extra.d.ts',b'owned'),('.next/types/extra.d.ts',b'\xff')]:
        bad=deepcopy(data); bad['generated_files'][name]=raw
        bad['envelope']['statement']['generated_inventory_sha256']=digest({p:sha(b) for p,b in bad['generated_files'].items()}); resign(bad,private)
        with pytest.raises(ValueError): verify(bad)
