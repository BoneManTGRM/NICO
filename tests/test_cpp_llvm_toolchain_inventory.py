"""Offline adversarial tests; synthetic indices never establish upstream trust."""
from copy import deepcopy
import gzip
import hashlib
import pytest
from scripts.cpp_llvm_toolchain_inventory import PACKAGES, INDEX_PATH, release_index, select_packages


def index(overrides=None):
    rows=[]
    for name in PACKAGES:
        fields={'Package':name, 'Version':'1:17.0.6~++20231209124227+6009708b4367-1~exp1',
                'Architecture':'amd64','Size':'1024','Filename':'pool/main/l/llvm-toolchain-17/'+name+'_17.0.6_amd64.deb',
                'SHA256':'a'*64,'Depends':'libc6 (>= 2.34)'}
        if overrides: fields.update(overrides)
        rows.append('\n'.join(k+': '+v for k,v in fields.items()))
    return gzip.compress(('\n\n'.join(rows)+'\n\n').encode(),mtime=0)


def test_signed_release_binds_exact_compressed_index_bytes():
    raw=index(); release=('SHA256:\n '+hashlib.sha256(raw).hexdigest()+' '+str(len(raw))+' '+INDEX_PATH+'\n').encode()
    release_index(release,raw)
    with pytest.raises(ValueError): release_index(release,raw+b'x')
    with pytest.raises(ValueError): release_index(release+release,raw)


def test_fixed_tool_population_has_exact_package_bytes_but_is_not_installation():
    selected=select_packages(index())
    assert [r['package'] for r in selected]==list(PACKAGES)
    assert all(r['sha256']=='a'*64 and r['bytes']==1024 for r in selected)
    assert all(r['url'].startswith('https://apt.llvm.org/bookworm/pool/') for r in selected)


@pytest.mark.parametrize('mutation', [{'Architecture':'arm64'},{'Version':'1:18.0.6+date'},
    {'Size':'0'},{'Size':'999999999999'},{'Filename':'../../arbitrary.deb'},
    {'Filename':'pool/main/a/../bad.deb'},{'SHA256':'not a digest'},
    {'Package':'different'},{'Package':'clang-17'}])
def test_unbound_ambiguous_or_unbounded_packages_are_rejected(mutation):
    with pytest.raises(ValueError): select_packages(index(mutation))


def test_oversized_decompression_rejected():
    with pytest.raises(ValueError): select_packages(gzip.compress(b'x'*(8*1024*1024+1)))


def fake_upstream(monkeypatch, *, wrong_key=False, wrong_signer=False, corrupt_index=False):
    from scripts import cpp_llvm_toolchain_inventory as module
    from types import SimpleNamespace
    raw=index()
    release=('SHA256:\n '+hashlib.sha256(raw).hexdigest()+' '+str(len(raw))+' '+INDEX_PATH+'\n').encode()
    def fetch(url,destination,**kwargs):
        data=raw+(b'x' if corrupt_index else b'') if url==module.INDEX_URL else b'synthetic-public-key' if url==module.KEY_URL else b'synthetic-signed-release'
        destination.write_bytes(data);return data
    def run(args,**kwargs):
        assert kwargs['check'] is True and kwargs['timeout']==5
        if '--show-keys' in args:
            fpr='0'*40 if wrong_key else module.FINGERPRINT
            return SimpleNamespace(stdout=('fpr:::::::::'+fpr+':\n').encode())
        if args[0]=='gpgv':
            from pathlib import Path
            Path(args[args.index('--output')+1]).write_bytes(release)
            fpr='0'*40 if wrong_signer else module.FINGERPRINT
            return SimpleNamespace(stdout=('[GNUPG:] VALIDSIG '+fpr+' 2026-09-22 0 0 4 0 1 10 01 '+fpr+'\n').encode())
        return SimpleNamespace(stdout=b'')
    monkeypatch.setattr(module,'fetch',fetch)
    monkeypatch.setattr(module.subprocess,'run',run)
    return module


def test_verified_pipeline_still_does_not_install_or_qualify_tools(monkeypatch,tmp_path):
    module=fake_upstream(monkeypatch)
    result=module.inventory(tmp_path/'inventory')
    assert result['status']=='AUTHENTICATED_INVENTORY'
    assert result['installed'] is False and result['production_qualified'] is False
    assert result['dependency_closure_qualified'] is False


@pytest.mark.parametrize('failure',['wrong_key','wrong_signer','corrupt_index'])
def test_each_authentication_link_fails_closed_and_retains_failure(monkeypatch,tmp_path,failure):
    import json
    module=fake_upstream(monkeypatch,**{failure:True})
    output=tmp_path/'inventory'
    with pytest.raises(ValueError):module.inventory(output)
    result=json.loads((output/'receipt.json').read_text())
    assert result['status']=='UNPROVEN' and result['installed'] is False
    assert 'packages' not in result


def test_arbitrary_repository_url_is_rejected_before_http(tmp_path):
    import time
    from scripts.cpp_llvm_toolchain_inventory import fetch
    with pytest.raises(ValueError,match='destination_invalid'):
        fetch('https://example.invalid/index',tmp_path/'not-written',limit=1024,deadline=time.monotonic()+2)
    assert not (tmp_path/'not-written').exists()
