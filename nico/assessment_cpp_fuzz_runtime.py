"""Host-owned fuzz orchestration; all target code runs in disposable runtime UIDs.

The existing leased controller supplies timeout/cancellation and removes the
whole container. These fixed setup programs never execute assessed bytes as
root or the analyst. Immutable snapshots precede separately owned executions.
"""
from __future__ import annotations
import base64
import hashlib
import json
import time

from nico.assessment_cpp_fuzz import (
    _digest, inspect_symbols, phase_name, runtime_user, target_arguments,
    validate_plan, validate_snapshots,
)
from nico.assessment_cpp_native_tests import PROBE_PROGRAM

SETUP_PROGRAM = r'''
import json, os, pathlib, stat, sys
p = json.loads(sys.stdin.buffer.read(262145))
if os.getuid() != 0 or os.getgid() != 0 or not 1 <= len(p['targets']) <= 2:
    raise ValueError('fuzz_setup_identity')
snap = pathlib.Path('/work/fuzz-snapshots'); snap.mkdir(mode=0o755)
runs = pathlib.Path('/work/fuzz-runs'); runs.mkdir(mode=0o1777); runs.chmod(0o1777)
for i, target in enumerate(p['targets']):
    (snap / ('t' + str(i))).mkdir(mode=0o755)
print('fuzz_snapshot_destinations_ready')
'''

RUNTIME_SETUP_PROGRAM = r'''
import json, os, pathlib, re, stat, sys
name = sys.argv[1]
match = re.fullmatch(r't([01])-(seed([0-7])|campaign)', name)
if match is None:
    raise ValueError('fuzz_runtime_directory_invalid')
uid = 3000 + int(match[1]) * 16 + (8 if match[2] == 'campaign' else int(match[3]))
if os.getuid() != uid or os.getgid() != uid:
    raise ValueError('fuzz_runtime_setup_identity')
root = pathlib.Path('/work/fuzz-runs')
info = root.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o1777:
    raise ValueError('fuzz_runtime_setup_parent')
path = root / name
# Each final runtime UID creates its own directories before any assessed
# command. CAP_CHOWN is neither present nor needed. Refuse existing paths.
path.mkdir(mode=0o755)
(path / 'corpus').mkdir(mode=0o755)
for directory in (path, path / 'corpus'):
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != uid or stat.S_IMODE(info.st_mode) != 0o755:
        raise ValueError('fuzz_runtime_setup_ownership')
print(json.dumps({'name': name, 'uid': uid, 'gid': uid}, sort_keys=True))
'''

SEAL_SETUP_PROGRAM = r'''
import os, pathlib, stat
if os.getuid() != 0 or os.getgid() != 0:
    raise ValueError('fuzz_setup_identity')
root = pathlib.Path('/work/fuzz-runs')
info = root.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o1777:
    raise ValueError('fuzz_runtime_setup_parent')
root.chmod(0o555)
print('fuzz_runtime_population_sealed')
'''


def prepare_workspace(require, container, plan):
    """Create one isolated phase directory per runtime UID with no capabilities.

    Only fixed trusted setup code is invoked here, before any project command.
    Native target execution still uses the existing immutable binary snapshots.
    """
    result = require(['docker', 'exec', '--user=0:0', '--interactive', container,
        'python3', '-I', '-S', '-c', SETUP_PROGRAM], data=json.dumps(plan).encode())
    if result.strip() != b'fuzz_snapshot_destinations_ready':
        raise ValueError('worker_fuzz_setup_unverified')
    for i, target in enumerate(plan['targets']):
        for j in [*range(len(target['corpus'])), 8]:
            name = 't' + str(i) + '-' + ('campaign' if j == 8 else 'seed' + str(j))
            uid = 3000 + i * 16 + j
            result = require(['docker', 'exec', '--user=' + str(uid) + ':' + str(uid),
                container, 'python3', '-I', '-S', '-c', RUNTIME_SETUP_PROGRAM, name])
            if json.loads(result) != {'name': name, 'uid': uid, 'gid': uid}:
                raise ValueError('worker_fuzz_setup_unverified')
    result = require(['docker', 'exec', '--user=0:0', container,
        'python3', '-I', '-S', '-c', SEAL_SETUP_PROGRAM])
    if result.strip() != b'fuzz_runtime_population_sealed':
        raise ValueError('worker_fuzz_setup_unverified')


SNAPSHOT_PROGRAM = r'''
import hashlib, json, os, pathlib, re, stat, sys
request = json.loads(sys.stdin.buffer.read(262145))
if os.getuid() != 0: raise ValueError('fuzz_snapshot_identity')
def read(path, limit):
    parts = pathlib.PurePosixPath(path).parts
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 1 <= before.st_size <= limit:
                raise ValueError('fuzz_snapshot_input_invalid')
            data = handle.read(limit + 1); after = os.fstat(handle.fileno())
        if len(data) != before.st_size or any(getattr(before, k) != getattr(after, k) for k in ('st_size','st_mtime_ns','st_ctime_ns','st_nlink')):
            raise ValueError('fuzz_snapshot_input_changed')
        return data
    finally: os.close(fd)
def safe(path):
    return isinstance(path, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]{0,499}', path) and all(p not in ('','.','..','.git') for p in path.split('/'))
result = {}
for i, target in enumerate(request['plan']['targets']):
    source = target['binary']
    if not safe(source): raise ValueError('fuzz_snapshot_path')
    root = pathlib.Path('/work/fuzz-snapshots/t' + str(i))
    info = root.stat()
    if root.is_symlink() or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755:
        raise ValueError('fuzz_snapshot_destination')
    binary = read('/work/fuzz-build/' + source, 67108864)
    if binary[:6] != b'\x7fELF\x02\x01' or binary[16:20] not in (b'\x02\x00\x3e\x00',b'\x03\x00\x3e\x00'):
        raise ValueError('fuzz_snapshot_binary_invalid')
    path = root / 'program'
    with path.open('xb') as handle: handle.write(binary)
    path.chmod(0o555)
    corpus = {}
    (root / 'seeds').mkdir(mode=0o755)
    for j, source in enumerate(target['corpus']):
        if not safe(source): raise ValueError('fuzz_snapshot_path')
        data = read('/work/source/' + source, request['plan']['max_len'])
        sha = hashlib.sha256(data).hexdigest()
        if sha != request['hashes'][source]: raise ValueError('fuzz_snapshot_corpus_changed')
        for dest in (root / ('s' + str(j)), root / 'seeds' / ('s' + str(j))):
            with dest.open('xb') as handle: handle.write(data)
            dest.chmod(0o444)
        corpus[source] = {'sha256':sha,'bytes':len(data)}
    (root / 'seeds').chmod(0o555); root.chmod(0o555)
    result['t' + str(i)] = {'path':str(path),'sha256':hashlib.sha256(binary).hexdigest(),
        'bytes':len(binary),'uid':0,'mode':0o555,'corpus':corpus}
print(json.dumps(result,sort_keys=True))
'''

VERIFY_PROGRAM = r'''
import hashlib, json, os, pathlib, stat, sys
expected = json.loads(sys.stdin.buffer.read(65537))
root = pathlib.Path(expected['path']).parent
if os.getuid() != 0 or root.parent != pathlib.Path('/work/fuzz-snapshots') or root.is_symlink():
    raise ValueError('fuzz_verify_identity')
for parent in (root, root / 'seeds'):
    info = parent.stat()
    if parent.is_symlink() or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o555:
        raise ValueError('fuzz_verify_parent')
def verified(path, size, digest, mode):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno()); data = handle.read(size + 1)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('fuzz_verify_changed')
verified(root / 'program',expected['bytes'],expected['sha256'],0o555)
for i, data in enumerate(expected['corpus'].values()):
    for path in (root / ('s' + str(i)),root / 'seeds' / ('s' + str(i))):
        verified(path,data['bytes'],data['sha256'],0o444)
print(json.dumps(expected,sort_keys=True))
'''

INSPECT_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, resource, subprocess, sys, tempfile
path = sys.argv[1]
if os.getuid() != 1001 or re.fullmatch(r'/work/fuzz-snapshots/t[01]/program',path) is None:
    raise ValueError('fuzz_inspect_identity')
resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152))
def tool(argv,maximum):
    with tempfile.TemporaryFile(dir='/work/analysis') as output:
        result = subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
            timeout=5,check=False,env={'PATH':'/usr/bin:/bin','LANG':'C','LD_LIBRARY_PATH':'/usr/local/lib64:/usr/local/lib'})
        output.seek(0); raw = output.read(maximum + 1)
    if result.returncode != 0 or len(raw) > maximum: raise ValueError('fuzz_inspection_failed')
    return raw
raw = tool(['/usr/bin/nm','--defined-only',path],2097152)
selected = set()
for line in raw.splitlines():
    match = re.fullmatch(rb'[0-9a-fA-F]+[ \t]+[TtWw][ \t]+([A-Za-z0-9_]+)',line.strip())
    if match:
        symbol = match[1].decode()
        if symbol in {'LLVMFuzzerTestOneInput','LLVMFuzzerRunDriver','__sanitizer_cov_8bit_counters_init','__asan_init'}:
            selected.add(symbol)
dynamic = tool(['/usr/bin/readelf','-dW',path],65536)
interpreter = tool(['/usr/bin/readelf','-lW',path],65536)
print(json.dumps({'symbols':sorted(selected),'nm_sha256':hashlib.sha256(raw).hexdigest(),'nm_bytes':len(raw),
    'dynamic':base64.b64encode(dynamic).decode(),'interpreter':base64.b64encode(interpreter).decode()},sort_keys=True))
'''

ARTIFACT_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, stat, sys
path, limit = sys.argv[1], int(sys.argv[2])
if os.getuid() != 0 or re.fullmatch(r'/work/fuzz-runs/t[01]-(?:seed[0-7]|campaign)/failure.bin',path) is None:
    raise ValueError('fuzz_artifact_path')
fd = os.open('/',os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in pathlib.PurePosixPath(path).parts[1:-1]:
        child = os.open(part,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,dir_fd=fd)
        os.close(fd);fd=child
    try: leaf = os.open('failure.bin',os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,dir_fd=fd)
    except FileNotFoundError:
        result={'present':False,'bytes':0,'sha256':None,'data':''}
    else:
        with os.fdopen(leaf,'rb') as handle:
            info=os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit: raise ValueError('fuzz_artifact_limit')
            data=handle.read(limit+1)
        if len(data)>limit: raise ValueError('fuzz_artifact_limit')
        result={'present':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode()}
finally:os.close(fd)
print(json.dumps(result,sort_keys=True))
'''


def _json_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def operation_specs(plan, source_hashes):
    plan = validate_plan(plan, source_hashes)
    specs = []
    def add(name,argv,user,data=None,**extra):
        specs.append({'id':name,'argv':argv,'user':user,'data':data,
            'input_sha256':hashlib.sha256(data).hexdigest() if data is not None else None,**extra})
    hashes = {p:source_hashes[p] for t in plan['targets'] for p in t['corpus']}
    add('snapshot',['python3','-I','-S','-c',SNAPSHOT_PROGRAM],'0:0',_json_bytes({'plan':plan,'hashes':hashes}))
    for i,target in enumerate(plan['targets']):
        snapshot=f'/work/fuzz-snapshots/t{i}/program'
        add(f't{i}-inspect',['python3','-I','-S','-c',INSPECT_PROGRAM,snapshot],'1001:1001')
        for phase,j in [('replay',j) for j in range(len(target['corpus']))]+[('campaign',None)]:
            name=phase_name(i,phase,j);user=runtime_user(i,phase,j)
            add(name+'-probe',['python3','-I','-S','-c',PROBE_PROGRAM,snapshot],user,phase=name)
            add(name+'-run',target_arguments(plan,i,phase=phase,seed_index=j),user,phase=name)
            # Expected snapshot bytes are unknown before acquisition; the wrapper
            # still binds their actual input digest in the native observation.
            add(name+'-after',['python3','-I','-S','-c',VERIFY_PROGRAM],'0:0',snapshot_input=i)
            add(name+'-artifact',['python3','-I','-S','-c',ARTIFACT_PROGRAM,
                '/work/fuzz-runs/'+name+'/failure.bin',str(plan['max_len'])],'0:0')
    return specs


def run_fuzz(invoke, container, plan, source_hashes):
    plan=validate_plan(plan,source_hashes); specs=operation_specs(plan,source_hashes)
    result={'schema':'nico.cpp-fuzz-native.v1','plan_sha256':_digest(plan),'error':None,
        'operations':[{'id':s['id'],'invocation':s['argv'],'user':s['user'],
            'input_sha256':s['input_sha256'],'attempted':False,'exit_code':None,'timed_out':False,
            'output_truncated':False,'duration_ms':0,'output':'','output_sha256':hashlib.sha256(b'').hexdigest()} for s in specs]}
    snapshots=None; last_failed=False
    try:
        for spec,row in zip(specs,result['operations']):
            data=spec['data']
            if 'snapshot_input' in spec:
                data=_json_bytes(snapshots[f"t{spec['snapshot_input']}"])
                row['input_sha256']=hashlib.sha256(data).hexdigest()
            prefix=['docker','exec','--user='+spec['user']]
            if data is not None:prefix+=['--interactive']
            if 'phase' in spec:
                name=spec['phase']; i=int(name[1])
                env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C','HOME':'/work/fuzz-runs/'+name,
                    'TMPDIR':'/work/fuzz-runs/'+name,'LD_LIBRARY_PATH':'/usr/local/lib64:/usr/local/lib',
                    'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1',
                    **plan['targets'][i]['environment']}
                prefix+=['--workdir=/work/fuzz-runs/'+name]
                argv=['/usr/bin/env','-i',*[k+'='+v for k,v in sorted(env.items())],*spec['argv']]
            else:argv=spec['argv']
            start=time.monotonic()
            output=invoke([*prefix,container,*argv],data=data,max_output=65536,seconds=15)
            row.update(attempted=True,exit_code=output['exit_code'],timed_out=output['timed_out'],
                output_truncated=output['output_truncated'],duration_ms=int((time.monotonic()-start)*1000),
                output=base64.b64encode(output['output']).decode(),output_sha256=hashlib.sha256(output['output']).hexdigest())
            if output['timed_out'] or output['output_truncated']:
                result['error']='worker_fuzz_interrupted';break
            good=output['exit_code']==0
            if row['id']=='snapshot':
                if not good:raise ValueError('snapshot_failed')
                snapshots=validate_snapshots(json.loads(output['output']),plan,source_hashes)
            elif row['id'].endswith('-inspect'):
                if not good or not inspect_symbols(json.loads(output['output'])):raise ValueError('inspection_failed')
            elif row['id'].endswith('-probe'):
                name=spec['phase']; i=int(name[1]);value=json.loads(output['output']);uid=int(spec['user'].split(':')[0])
                expected={'uid':uid,'gid':uid,'write_denied':True,'binary_sha256':snapshots[f't{i}']['sha256'],
                    'no_new_privileges':True,'capabilities':0,'credential_environment_absent':True}
                if not good or value!=expected:raise ValueError('probe_failed')
            elif row['id'].endswith('-after'):
                if not good or json.loads(output['output'])!=snapshots[f"t{spec['snapshot_input']}"]:raise ValueError('snapshot_changed')
            elif row['id'].endswith('-run'):
                last_failed=not good
            elif row['id'].endswith('-artifact'):
                if not good:raise ValueError('artifact_failed')
                if last_failed:
                    result['error']='worker_fuzz_native_failed';break
    except (ValueError,KeyError,TypeError,OSError):
        result['error']='worker_fuzz_controller_failed'
    return result
