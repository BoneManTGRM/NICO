"""Owned runtime opt-in controls, never an assessed source invocation."""
import inspect
import textwrap
from .binding import analyzer_environment


def owned_program(binding):
    return inspect.getsource(analyzer_environment) + '\n' + 'binding = ' + repr(binding) + '\n' + textwrap.dedent(r'''
        import os, subprocess, json, hashlib
        from pathlib import Path
        assert hashlib.sha256(Path('/usr/local/bin/cppcheck').read_bytes()).hexdigest()==binding['instrumented_binary_sha256']
        assert hashlib.sha256(Path('/opt/nico-clang-header-observer.so').read_bytes()).hexdigest()==binding['observer_sha256']
        argv=['/usr/local/bin/cppcheck','--xml','--enable=warning,style,performance,portability,information,missingInclude',
              '--check-level=exhaustive','--max-configs=1','--platform=unix64','-j1',
              '--showtime=file','--report-progress=1','/work/source/owned.cpp']
        # Deliberately hostile ambient value: the allowlisted environment must ignore it.
        os.environ['NICO_CPP_STAGE_COUNTERS']='1'
        base={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/work/analysis',
              'TMPDIR':'/work/analysis','LD_LIBRARY_PATH':'/usr/local/lib64:/usr/local/lib'}
        records=[]
        for enabled in (False,True):
            environment=analyzer_environment(argv,base,enabled,[argv])
            assert ('NICO_CPP_STAGE_COUNTERS' in environment)==enabled
            assert 'NICO_CPP_STAGE_COUNTERS' not in base
            value=subprocess.run(argv,env=environment,capture_output=True,timeout=20,cwd='/work/analysis')
            rows=[line for line in value.stderr.splitlines() if line.startswith(b'NICO_STAGE_V2 ')]
            assert value.returncode==0 and bool(rows)==enabled
            assert len(rows)<=128 and all(len(row)+1<=1024 for row in rows)
            records.append({'enabled':enabled,'exit_code':value.returncode,'stage_lines':len(rows),
                            'stdout_sha256':hashlib.sha256(value.stdout).hexdigest(),
                            'stderr_sha256':hashlib.sha256(value.stderr).hexdigest(),
                            'stdout':value.stdout.decode(errors='replace'),'stderr':value.stderr.decode(errors='replace')})
        print(json.dumps({'owned_stage_controls':records,'passed':True},sort_keys=True))
    ''')
