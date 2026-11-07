"""Build only the reviewed Clang observer using fixed authenticated SDK inputs."""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, stat, subprocess
from pathlib import Path

MANIFEST_SHA256='b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8'
SOURCE_SHA256='76ad9e51e0500a6d93fc81038ca7df6cb42c14d8d580b42f92b1281efa7124a1'
SDK_SHA256='76385517f23a58851167a04ef5ba1697830fe62e569acdf804eec708e063260b'
RUNTIME_SHA256='57c8fa1fb9dabce9c7e3f546ccb7d6fb549abece632742448272e10fabb66abb'

def stable(path,limit):
    path=Path(path)
    if path.is_symlink() or path.resolve(strict=True)!=path.absolute():raise ValueError('clang_header_build_path_invalid')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError('clang_header_build_size_invalid')
        raw=os.read(fd,limit+1);after=os.fstat(fd)
        keys=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if len(raw)!=before.st_size or keys(before)!=keys(after):raise ValueError('clang_header_build_changed')
        return raw
    finally:os.close(fd)

def build(source,sdk,runtime,output,*,run=subprocess.run):
    source,sdk,runtime,output=map(lambda path:Path(path).absolute(),(source,sdk,runtime,output))
    for directory,name,expected in [(source,'manifest.json',MANIFEST_SHA256),(source,'HeaderObserver.cpp',SOURCE_SHA256),
            (sdk,'lock.json',SDK_SHA256),(runtime,'lock.json',RUNTIME_SHA256)]:
        if hashlib.sha256(stable(directory/name,1024*1024)).hexdigest()!=expected:raise ValueError('clang_header_build_input_invalid')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(output)}
    version=run(['/usr/local/bin/g++','-dumpfullversion'],check=True,capture_output=True,timeout=5,env=env).stdout.strip()
    clang=run(['/usr/lib/llvm-17/bin/clang','-dumpversion'],check=True,capture_output=True,timeout=5,env=env).stdout.strip()
    if version!=b'14.2.0' or clang!=b'17.0.6':raise ValueError('clang_header_build_toolchain_invalid')
    binary=output/'observer.so'
    argv=['/usr/local/bin/g++','-std=c++17','-O1','-fPIC','-shared','-fno-rtti',
        '-I/usr/lib/llvm-17/include',str(source/'HeaderObserver.cpp'),'-o',str(binary)]
    run(argv,check=True,timeout=180,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    raw=stable(binary,4*1024*1024)
    if len(raw)<64 or raw[:6]!=b'\x7fELF\x02\x01' or raw[18:20]!=b'\x3e\x00':
        raise ValueError('clang_header_build_binary_invalid')
    binary.chmod(0o444)
    probe=output/'probe.cpp';probe.write_bytes(b'int nico_header_observer_build_probe() { return 0; }\n')
    trace=output/'probe.header.json';plist=output/'probe.plist';context=hashlib.sha256(probe.read_bytes()).hexdigest()
    argv=['/usr/lib/llvm-17/bin/clang++','-std=c++17','--analyze','-Xclang','-load','-Xclang',str(binary),
        '-Xanalyzer','-analyzer-checker=nico.HeaderEvidence','-Xanalyzer','-analyzer-output=plist-multi-file',
        '-fno-color-diagnostics',str(probe),'-o',str(plist)]
    observed=run(argv,check=True,capture_output=True,timeout=30,
        env={**env,'NICO_CLANG_HEADER_OUTPUT':str(trace),'NICO_CLANG_HEADER_CONTEXT':context})
    if len(observed.stdout)+len(observed.stderr)>65536:raise ValueError('clang_header_build_probe_output_invalid')
    trace_raw=stable(trace,1024*1024);document=json.loads(trace_raw)
    plist_raw=stable(plist,1024*1024);diagnostics=plistlib.loads(plist_raw)
    rows=document.get('files',[])
    if (document.get('schema')!='nico.clang-header-observer.v1' or document.get('clang_version')!='17.0.6'
            or document.get('context_id')!=context or document.get('source')!=str(probe)
            or document.get('standard')!='c++17' or document.get('translation_unit_started') is not True
            or document.get('translation_unit_ended') is not True or document.get('diagnostic_errors') is not False
            or document.get('observation_overflow') is not False or len(rows)!=1
            or rows[0].get('path')!=str(probe) or rows[0].get('ast_body_callbacks')!=1
            or diagnostics.get('diagnostics')!=[]):raise ValueError('clang_header_build_probe_invalid')
    (output/'startup-control.json').write_text(json.dumps({'schema':'nico.clang-header-startup.v1',
        'invocation':argv,'exit_code':observed.returncode,'source_sha256':context,
        'trace_sha256':hashlib.sha256(trace_raw).hexdigest(),'plist_sha256':hashlib.sha256(plist_raw).hexdigest(),
        'stdout_sha256':hashlib.sha256(observed.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(observed.stderr).hexdigest(),
        'scope':'Trusted fixed build probe only; not assessed-project, worker isolation or final qualification.'},indent=2)+'\n')
    receipt={'schema':'nico.clang-header-tool.v1','manifest_sha256':MANIFEST_SHA256,'source_sha256':SOURCE_SHA256,
        'sdk_lock_sha256':SDK_SHA256,'runtime_lock_sha256':RUNTIME_SHA256,'clang_version':'17.0.6',
        'plugin_sha256':hashlib.sha256(raw).hexdigest(),'compiler_version':'14.2.0','qualification_completed':False}
    (output/'receipt.json').write_text(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','sdk','runtime','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.source,a.sdk,a.runtime,a.output)))
