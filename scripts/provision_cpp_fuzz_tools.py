"""Download the fixed LLVM 17 image inputs; verify bytes, never run install hooks.

LLVM entries were recovered from the retained signature-verified upstream index.
The two Debian runtime-library hashes are pinned to Debian's package metadata.
Tools are extracted only in the disposable tool-image build, without networking.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

LOCK = Path(__file__).resolve().parents[1] / 'docker/assessment-llvm17.lock.json'
PACKAGES = {'clang-17', 'libclang-cpp17', 'libllvm17', 'libclang-common-17-dev',
            'libclang1-17', 'libclang-rt-17-dev', 'llvm-17-linker-tools', 'libz3-4', 'libedit2'}


def validate_lock(value):
    if not isinstance(value, dict) or value.get('schema') != 'nico.llvm17-package-lock.v1':
        raise ValueError('fuzz_tool_lock_invalid')
    rows = value.get('packages')
    if (not isinstance(rows, list) or len(rows) != len(PACKAGES)
            or any(not isinstance(r, dict) for r in rows)
            or {r.get('package') for r in rows} != PACKAGES):
        raise ValueError('fuzz_tool_population_invalid')
    total = 0
    for row in rows:
        size, url = row.get('bytes'), row.get('url')
        if not isinstance(url, str): raise ValueError('fuzz_tool_url_invalid')
        parsed = urlsplit(url)
        allowed = ('apt.llvm.org', '/bookworm/pool/main/l/llvm-toolchain-17/') if row['package'] not in {'libz3-4','libedit2'} else ('deb.debian.org', '/debian/pool/main/')
        if (parsed.scheme != 'https' or parsed.netloc != allowed[0]
                or not parsed.path.startswith(allowed[1]) or not parsed.path.endswith('_amd64.deb')
                or parsed.query or parsed.fragment or '%' in parsed.path
                or any(p in {'.','..'} for p in parsed.path.split('/'))
                or type(size) is not int or not 1 <= size <= 80 * 1024 * 1024
                or row.get('architecture') != 'amd64' or not isinstance(row.get('sha256'), str)
                or re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is None):
            raise ValueError('fuzz_tool_lock_invalid')
        total += size
    if total > 200 * 1024 * 1024: raise ValueError('fuzz_tool_budget_invalid')
    return rows


def provision(destination, *, run=subprocess.run):
    value = json.loads(LOCK.read_bytes()); rows = validate_lock(value)
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {'schema':'nico.cpp-fuzz-tool-provisioning.v1','status':'UNPROVEN',
        'lock_sha256':hashlib.sha256(LOCK.read_bytes()).hexdigest(), 'packages':[],
        'installed':False,'target_executed':False}
    deadline = time.monotonic() + 90
    try:
        for row in rows:
            left = min(30, int(deadline-time.monotonic()))
            if left < 1: raise ValueError('fuzz_tool_download_deadline')
            path = destination / (row['package'] + '.deb')
            run(['curl','--disable','--fail','--silent','--show-error','--proto','=https','--tlsv1.2',
                 '--connect-timeout','3','--max-time',str(left),'--max-filesize',str(row['bytes']),
                 '--output',str(path),row['url']], check=True, timeout=left+1,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={'PATH':os.environ.get('PATH','/usr/bin:/bin')})
            if path.is_symlink() or not path.is_file() or path.stat().st_size != row['bytes']:
                raise ValueError('fuzz_tool_download_size_invalid')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != row['sha256']: raise ValueError('fuzz_tool_download_hash_invalid')
            result['packages'].append({'package':row['package'],'sha256':digest,'bytes':row['bytes']})
        (destination / 'SHA256SUMS').write_text(''.join(r['sha256']+'  '+r['package']+'.deb\n' for r in rows))
        result['status']='VERIFIED_TOOL_INPUTS'
    finally:
        (destination / 'receipt.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True)
    print(json.dumps({'status':provision(p.parse_args().destination)['status']}))
