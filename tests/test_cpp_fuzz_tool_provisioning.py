"""Offline tool-input checks; no downloads or package installation occur here."""
from copy import deepcopy
import hashlib
import json
import subprocess
import pytest
from scripts import provision_cpp_fuzz_tools as tool


def test_frozen_package_lock_is_complete_and_bounded():
    rows=tool.validate_lock(json.loads(tool.LOCK.read_bytes()))
    assert len(rows)==9
    assert sum(r['bytes'] for r in rows)<60*1024*1024


@pytest.mark.parametrize('change',[{'url':'https://example.invalid/package_amd64.deb'},
    {'url':'https://apt.llvm.org/bookworm/pool/main/l/llvm-toolchain-17/../x_amd64.deb'},
    {'url':'https://apt.llvm.org/bookworm/pool/main/l/llvm-toolchain-17/%2e%2e/x_amd64.deb'},
    {'sha256':'invalid'},{'bytes':True},{'bytes':0},{'bytes':999999999}, {'architecture':'arm64'}])
def test_untrusted_or_unbounded_lock_entries_are_rejected(change):
    value=json.loads(tool.LOCK.read_bytes());value['packages'][0].update(change)
    with pytest.raises(ValueError):tool.validate_lock(value)


def test_installer_downloads_no_hooks_and_rejects_wrong_bytes(tmp_path,monkeypatch):
    value=json.loads(tool.LOCK.read_bytes())
    for row in value['packages']:row.update(bytes=4,sha256=hashlib.sha256(b'test').hexdigest())
    lock=tmp_path/'lock.json';lock.write_text(json.dumps(value));monkeypatch.setattr(tool,'LOCK',lock)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        assert args[:2]==['curl','--disable'] and '--max-time' in args and '--max-filesize' in args
        assert '-L' not in args and kwargs['check'] and kwargs['timeout']<=31
        assert set(kwargs['env'])=={'PATH'}
        from pathlib import Path
        Path(args[args.index('--output')+1]).write_bytes(b'test')
    result=tool.provision(tmp_path/'inputs',run=run)
    assert result['status']=='VERIFIED_TOOL_INPUTS' and result['installed'] is False and len(calls)==9
    def bad(args,**kwargs):
        from pathlib import Path
        Path(args[args.index('--output')+1]).write_bytes(b'fake')
    with pytest.raises(ValueError,match='hash_invalid'):tool.provision(tmp_path/'bad',run=bad)
    assert json.loads((tmp_path/'bad/receipt.json').read_bytes())['status']=='UNPROVEN'
