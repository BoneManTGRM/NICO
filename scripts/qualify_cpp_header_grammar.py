"""Owned native grammar controls; successful small cases are not qualification."""
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

CASES = ('attribute', 'capnp', 'noexcept-instantiated', 'bitfield',
         'qualified-comparison', 'attribute-semantics', 'alias-shadow', 'alias-global',
         'alias-self-global', 'alias-chains', 'alias-before', 'alias-nested', 'alias-rhs',
         'alias-nonlexical', 'alias-absolute', 'alias-heavy', 'alias-index-scopes', 'alias-record-cache', 'alias-malformed',
         'malformed', 'missing', 'depth-limit')
FAILURES = {'attribute': 'syntaxError', 'capnp': 'syntaxError',
            'noexcept-instantiated': 'internalAstError', 'bitfield': 'syntaxError',
            'attribute-semantics': 'syntaxError', 'alias-shadow': 'syntaxError',
            'alias-global': 'syntaxError', 'alias-before': 'syntaxError',
            'alias-nested': 'syntaxError', 'alias-nonlexical': 'syntaxError',
            'alias-index-scopes': 'syntaxError', 'alias-record-cache': 'syntaxError'}


def image_argv(image, source, output, trace_name, flags):
    return ['docker', 'run', '--rm', '--network=none', '--read-only', '--memory=12g', '--cpus=2',
        '--user='+str(os.getuid())+':'+str(os.getgid()), '--cap-drop=ALL',
        '--security-opt=no-new-privileges', '--pids-limit=128',
        '--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=64m',
        '--mount=type=bind,src='+str(source)+',dst=/work/owned,readonly',
        '--mount=type=bind,src='+str(output)+',dst=/work/output',
        '--env=CPPCHECK_NICO_NATIVE_PROVENANCE='+trace_name, '--entrypoint=cppcheck', image, *flags]


def qualify(output, *, binary=None, image=None, before=False):
    assert bool(binary) != bool(image)
    output = Path(output).absolute(); output.mkdir(exist_ok=False, parents=True)
    source = output/'source'
    shutil.copytree(Path(__file__).resolve().parents[1]/'tests/fixtures/cpp/physical-header-grammar', source)
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    identity = {'inputs': {str(p.relative_to(source)): digest(p.read_bytes()) for p in source.rglob('*') if p.is_file()},
        'image': image, 'binary_sha256': digest(Path(binary).read_bytes()) if binary else None,
        'parallel': 2, 'case_seconds': 90, 'shared_seconds': 1020, 'memory_bytes': 12*1024**3,
        'before_repair': before, 'scope': 'owned_grammar_controls'}
    results = []; start = time.monotonic()
    def limit(): resource.setrlimit(resource.RLIMIT_AS, (12*1024**3, 12*1024**3))
    for case in CASES:
        unit = source/(case+'.cpp'); trace = output/(case+'.trace.xml'); xml = output/(case+'.xml')
        unit_name = '/work/owned/'+unit.name if image else str(unit)
        dump_case = case == 'attribute-semantics' or case.startswith('alias-')
        if dump_case:
            unit = output/unit.name; shutil.copyfile(source/unit.name, unit)
            unit_name = '/work/output/'+unit.name if image else str(unit)
        trace_name = '/work/output/'+trace.name if image else str(trace)
        xml_name = '/work/output/'+xml.name if image else str(xml)
        flags = ['--xml', '--enable=all', '--check-level=exhaustive', '--max-configs=1', '-j1',
                 '--platform=unix64', '--std=c++20', unit_name, '--output-file='+xml_name]
        if dump_case:
            flags += ['--dump', '-I'+('/work/owned' if image else str(source))]
        if image:
            argv = image_argv(image, source, output, trace_name, flags)
        else: argv = [str(Path(binary).resolve(strict=True)), *flags]
        t = time.monotonic(); remaining = 1020-(t-start); assert remaining > 0
        run = subprocess.run(argv, capture_output=True, timeout=min(90, remaining),
            env={**os.environ, 'CPPCHECK_NICO_NATIVE_PROVENANCE':trace_name}, preexec_fn=None if image else limit)
        (output/(case+'.stdout')).write_bytes(run.stdout); (output/(case+'.stderr')).write_bytes(run.stderr)
        assert run.returncode == 0, (case, run.returncode, run.stderr)
        locations = {('/work/owned/'+p.name if image else str(p)):
                     ('owned',p.name,digest(p.read_bytes())) for p in source.iterdir() if p.is_file()}
        if dump_case: locations[unit_name] = ('owned',unit.name,digest(unit.read_bytes()))
        proof = validate_header_trace(trace.read_bytes(), source=unit_name, locations=locations, standard='c++20')
        errors = ET.fromstring(xml.read_bytes()).findall('errors/error'); rules = [e.get('id') for e in errors]
        if before and case in FAILURES:
            assert FAILURES[case] in rules and not proof['normal_pass_completed'], (case,rules,proof)
        elif case in {'malformed', 'alias-malformed'}:
            assert 'syntaxError' in rules and not proof['normal_pass_completed']
        elif case == 'missing':
            assert 'missingInclude' in rules and proof['unavailable_inputs'] and not proof['normal_pass_completed']
        elif case == 'depth-limit':
            assert 'internalAstError' in rules and not proof['normal_pass_completed']
            assert any('maximum AST depth exceeded' in e.get('msg','') for e in errors)
        else:
            assert proof['normal_pass_completed'] and not proof['unavailable_inputs'], (case,rules,proof)
            if case != 'alias-absolute':
                assert 'nullPointer' in rules, (case,rules)
            if case == 'attribute-semantics':
                functions = ET.fromstring(Path(str(unit)+'.dump').read_bytes()).findall('.//function')
                operators = [f for f in functions if f.get('name') == 'operator[]']
                assert len(operators) == 2
                assert [f.get('isAttributeNoreturn') for f in operators] == ['true',None]
                assert 'missingReturn' in rules  # The unannotated function remains a finding.
            expected_findings = {'alias-global': 2, 'alias-self-global': 2, 'alias-chains': 4, 'alias-before': 2, 'alias-nested': 2, 'alias-rhs': 2, 'alias-heavy': 1, 'alias-index-scopes': 3, 'alias-record-cache': 3}
            if before and case == 'alias-chains':
                expected_findings[case] = 2
            if case in expected_findings:
                assert rules.count('nullPointer') == expected_findings[case], (case, rules)
            if case in {'alias-before', 'alias-nested', 'alias-nonlexical', 'alias-index-scopes', 'alias-record-cache'}:
                tokens = ET.fromstring(Path(str(unit)+'.dump').read_bytes()).findall('.//tokenlist/token')
                calls = [i for i,t in enumerate(tokens) if t.get('str') == 'now' and i > 0 and tokens[i-1].get('str') == '::']
                assert calls
                for i in calls:
                    assert [t.get('str') for t in tokens[i-4:i]] == ['Model', '::', 'Clock', '::'], (case,i)
            if case == 'alias-absolute':
                tokens = ET.fromstring(Path(str(unit)+'.dump').read_bytes()).findall('.//tokenlist/token')
                for name in ('explicit_pointer', 'relative_pointer'):
                    uses = [t for t in tokens if t.get('str') == name]
                    assert uses, (case,name)
                    assert all(t.get('valueType-pointer') == '1' for t in uses), (case,name)
            header = source/(case+'.h')
            if header.exists():
                header_name = '/work/owned/'+header.name if image else str(header)
                assert header_name in proof['normal_pass_token_files']
                assert case == 'alias-absolute' or any(e.get('id') == 'nullPointer' and any(l.get('file') == header_name for l in e.findall('location')) for e in errors)
        results.append({'case':case,'argv':argv,'duration_ms':int((time.monotonic()-t)*1000),
            'exit_code':run.returncode,'rules':rules,'header_evidence':proof})
    report = {'identity':identity,'cases':results,'full_project_qualified':False}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--binary');group.add_argument('--image')
    parser.add_argument('--before',action='store_true');parser.add_argument('--output',required=True)
    args=parser.parse_args();result=qualify(args.output,binary=args.binary,image=args.image,before=args.before)
    print(json.dumps([(v['case'],v['header_evidence']['normal_pass_completed']) for v in result['cases']]))


if __name__=='__main__': main()
