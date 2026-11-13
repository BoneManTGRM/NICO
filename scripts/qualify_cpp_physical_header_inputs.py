"""Execute an owned physical-header omission reproducer with the pinned analyzer.

A library model is never credited as an entered/parsed physical header. This
control proves one input mechanism, not full-project coverage or performance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time
from xml.etree import ElementTree as ET
from nico.assessment_cpp_header_evidence import validate_header_trace


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def qualify(binary, output):
    binary, output = Path(binary).resolve(strict=True), Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/cpp/physical-header-inputs'
    source = output/'source'; shutil.copytree(fixture, source)
    public = source/'public/stdint.h'; body = public.read_bytes()
    identity = {'analyzer_binary_sha256': digest(binary.read_bytes()),
        'tool_version': subprocess.check_output([str(binary),'--version']).decode().strip(),
        'inputs': {str(p.relative_to(source)): digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()},
        'parallel': 2, 'case_seconds': 90, 'shared_execution_seconds': 1020,
        'memory_bytes': 12*1024**3, 'claim_scope': 'owned_input_mechanism_only'}
    assert identity['tool_version'] == 'Cppcheck 2.17.1'
    start = time.monotonic(); results = []
    def limit():
        resource.setrlimit(resource.RLIMIT_AS, (12*1024**3,12*1024**3))
    for label, relative, present in [('before','unit.cpp',False),('after','unit.cpp',True),
                                    ('generated-after','generated/unit.cpp',True),('missing-input','unit.cpp',False)]:
        if present: public.write_bytes(body)
        else: public.unlink(missing_ok=True)
        unit = source/relative; trace=output/(label+'.trace.xml'); xml=output/(label+'.xml')
        argv = [str(binary),'--xml','--enable=warning,style,performance,portability,information,missingInclude',
            '--check-level=exhaustive','--max-configs=1','--platform=unix64','-j1','--std=c++20',
            '-I'+str(source/'public'),'-I'+str(source),str(unit),'--output-file='+str(xml)]
        remaining = 1020-(time.monotonic()-start)
        assert remaining>0
        t=time.monotonic()
        run=subprocess.run(argv,env={**os.environ,'CPPCHECK_NICO_NATIVE_PROVENANCE':str(trace)},
            capture_output=True,timeout=min(90,remaining),preexec_fn=limit)
        assert run.returncode == 0, (label, run.returncode, run.stderr.decode(errors='replace'))
        (output/(label+'.stdout')).write_bytes(run.stdout)
        (output/(label+'.stderr')).write_bytes(run.stderr)
        locations={str(p): ('owned',str(p.relative_to(source)),digest(p.read_bytes()))
                   for p in source.rglob('*') if p.is_file()}
        raw=trace.read_bytes(); proof=validate_header_trace(raw,source=str(unit),locations=locations,standard='c++20')
        errors=ET.fromstring(xml.read_bytes()).findall('errors/error')
        rules=[e.get('id') for e in errors]
        assert proof['normal_pass_completed'] is present
        assert bool(proof['unavailable_inputs']) is not present
        if present:
            assert str(public) in proof['normal_pass_token_files']
            assert 'nullPointer' in rules, rules
            assert not any(r.startswith('missingInclude') for r in rules)
        else: assert 'missingIncludeSystem' in rules
        negatives={}
        if present:
            doc=ET.fromstring(raw);doc.find('file_end').set('normal_return','false')
            negatives['incomplete_return_no_credit']=not validate_header_trace(ET.tostring(doc),source=str(unit),locations=locations,standard='c++20')['normal_pass_completed']
            for key,kwargs in [('wrong_source',{'source':str(source/'wrong.cpp')}),('wrong_language',{'standard':'c++17'}),('unbound_header',{'locations':{k:v for k,v in locations.items() if k!=str(public)}})]:
                args=dict(source=str(unit),locations=locations,standard='c++20');args.update(kwargs)
                try: validate_header_trace(raw,**args)
                except ValueError: negatives[key]=True
                else: negatives[key]=False
            assert all(negatives.values())
        results.append({'label':label,'source':relative,'duration_ms':int((time.monotonic()-t)*1000),
            'invocation':argv,'exit_code':run.returncode,'header':proof,'rules':rules,'negative_controls':negatives,
            'diagnostics_sha256':digest(xml.read_bytes())})
    report={'identity':identity,'cases':results,'full_project_qualified':False,'production_qualified':False}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(); result=qualify(args.binary,args.output)
    print(json.dumps({'cases':[(v['label'],v['header']['normal_pass_completed'],v['rules']) for v in result['cases']],
                      'full_project_qualified':False}))

if __name__=='__main__':main()
