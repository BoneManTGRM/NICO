"""Owned parser equivalence and parent-only producer comparison; root executes."""
import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RUNNER = Path('/workspace/work/cpp_recovery/c33-static-stage-runner/static_stage_diagnostic.py')
RUNNER_SHA = '80c301fa846cd087606910e5a76998ffc63592f6a78469417eea9e2de2989d3b'
BASE_SOURCE = Path('/workspace/work/v17-controller-repair/source/nico/assessment_cpp_project_compiler.py')
BASE_SHA = 'be5b8be8386189af7f51e2ce47681b181a6c71a5e8384146da6deb8289e81276'
CANDIDATE = HERE/'source/nico/assessment_cpp_project_compiler.py'
CANDIDATE_SHA = '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8'
PARENT = 'f0919654edd719059ea03319981b13f46ba70a88'
PARENT_TREE = 'b9e200f62b9b2db9c6488326826ad8ae393418d0'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def require(ok,code):
    if not ok:
        raise ValueError(code)

def bound(path,digest):
    raw=path.read_bytes()
    require(sha(raw)==digest,'source_hash_mismatch:'+str(path))
    return raw

def outcome(function,*values,**kwargs):
    try:
        return {'kind':'return','value':function(*values,**kwargs)}
    except (ValueError,UnicodeError,TypeError,KeyError) as error:
        return {'kind':'raise','type':type(error).__name__,'message':str(error)}

def embedded(module):
    # Remove only the stdin execution entrypoint; keep the actual worker definitions.
    tree=ast.parse(module.PROGRAM)
    last=tree.body.pop()
    require(isinstance(last,ast.Expr) and isinstance(last.value,ast.Call)
        and isinstance(last.value.func,ast.Name) and last.value.func.id=='run_project_compiler',
        'worker_entrypoint_shape_changed')
    scope={'__name__':'owned_embedded_compiler_definitions'}
    exec(compile(tree,'owned_hash_bound_compiler_PROGRAM','exec'),scope)
    return scope['_dependency_populations']

def fixtures():
    digest='1'*64
    request={'targets':{'src/unit.cpp':digest},
             'generated_files':{'src/generated.h':{'sha256':'2'*64,'bytes':7}}}
    def row(name,body,accepted):
        return {'name':name,'raw':b'nico_unit: '+body,'request':request,'accepted':accepted}
    rows=[
        row('simple_original',b'/work/source/src/unit.cpp',True),
        row('simple_generated',b'/work/analysis/generated-baseline/src/generated.h',True),
        row('simple_system',b'/usr/include/stdio.h',True),
        row('space_tab_CR_LF',b'/usr/a.h \t\r\n /usr/b.h',True),
        row('line_continuation',b'/usr/a.h \\\n /usr/b.h',True),
        row('quoted_system_space',b'"/usr/header with space.h"',True),
        row('quoted_original',b'"/work/source/src/unit.cpp"',True),
        row('adjacent_quote_concatenation',b'/usr/"include"/stdio.h',True),
        row('single_quoted_system',b"'/usr/header with space.h'",True),
        row('escaped_space',b'/usr/header\\ with\\ space.h',True),
        row('escaped_backslash',b'"/usr/header\\\\name.h"',True),
        row('Unicode_nonseparator', '/usr/include/é.h'.encode(),True),
        row('Unicode_whitespace_stays_inside_token', '/usr/a\u2003b.h'.encode(),True),
        row('Unicode_NBSP_stays_inside_token', '/usr/a\u00a0b.h'.encode(),True),
        row('vertical_tab_rejects',b'/usr/a\x0bb.h',False),
        row('form_feed_rejects',b'/usr/a\x0cb.h',False),
        row('quoted_tab_rejects',b'"/usr/a\tb.h"',False),
        row('unclosed_double_quote',b'"/usr/a.h',False),
        row('unclosed_single_quote',b"'/usr/a.h",False),
        row('trailing_escape',b'/usr/a.h\\',False),
        row('hash_is_literal_comments_false',b'/usr/a#b.h',True),
        row('hash_separate_relative_token_rejects',b'/usr/a.h # /usr/b.h',False),
        row('relative_path_rejects',b'src/unit.cpp',False),
        row('double_slash_literal_rejects',b'//usr/include/stdio.h',False),
        row('colon_rejects',b'/usr/include/stdio:h',False),
        row('other_control_rejects',b'/usr/a\x01b.h',False),
        row('internal_normalization_preserved',b'/work/source/src/../src/unit.cpp',True),
        row('namespace_escape_rejects',b'/work/source/../../usr/include/stdio.h',False),
        row('mutable_path_rejects',b'/tmp/untrusted.h',False),
        row('unbound_original_rejects',b'/work/source/src/missing.h',False),
        row('unbound_generated_rejects',b'/work/analysis/generated-baseline/src/missing.h',False),
        row('all_namespaces',b'/work/source/src/unit.cpp /work/analysis/generated-baseline/src/generated.h /usr/x.h',True),
        row('empty_body',b'',False),
        row('duplicate_paths_preserved',b'/usr/x.h /usr/x.h /work/source/src/unit.cpp /work/source/src/unit.cpp',True),
        row('token_limit20000',b' '.join([b'/usr/x']*20000),True),
        row('token_limit20001',b' '.join([b'/usr/x']*20001),False),
    ]
    rows += [
        {'name':'empty_bytes','raw':b'','request':request,'accepted':False},
        {'name':'NUL_rejects','raw':b'nico_unit: /usr/a\0b.h','request':request,'accepted':False},
        {'name':'invalid_UTF8','raw':b'nico_unit: /usr/\xff','request':request,'accepted':False},
        {'name':'wrong_prefix','raw':b'other: /usr/a.h','request':request,'accepted':False},
        {'name':'oversize_bytes','raw':b'nico_unit: '+b'a'*262145,'request':request,'accepted':False},
    ]
    return rows

def equivalence(runner,prepared):
    from nico import assessment_cpp_project_compiler as base
    candidate=types.ModuleType('owned_candidate_compiler')
    candidate.__file__=str(CANDIDATE)
    sys.modules[candidate.__name__]=candidate
    # VerifiedLoader also binds inspect.getsource during PROGRAM construction.
    runner.VerifiedLoader(CANDIDATE,CANDIDATE_SHA).exec_module(candidate)
    pairs=[('module',base._dependency_populations,candidate._dependency_populations),
           ('PROGRAM',embedded(base),embedded(candidate))]
    request=base.project_compiler_request(prepared['database'],prepared['targets'],prepared['snapshot'],extended_budget=True)
    native=runner.strict_json(prepared['compiler_raw'])
    dependencies=[(i,base64.b64decode(row['dependency_bytes'],validate=True))
                  for i,row in enumerate(native['records']) if row['dependency_bytes']]
    require(len(dependencies)==576,'retained_nonempty_dependency_list_count_changed')
    initial_inputs=sha(prepared['compiler_raw']),sha(base._canonical(request))
    checks=[]; timings=[]
    for scope,before,after in pairs:
        expected=[]
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        for index,raw in dependencies:
            expected.append(outcome(before,raw,request))
        timings.append({'scope':scope,'variant':'baseline','wall_ms':(time.perf_counter_ns()-start)/1e6,
                        'process_cpu_ms':(time.process_time_ns()-cpu)/1e6})
        actual=[]
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        for index,raw in dependencies:
            actual.append(outcome(after,raw,request))
        timings.append({'scope':scope,'variant':'candidate','wall_ms':(time.perf_counter_ns()-start)/1e6,
                        'process_cpu_ms':(time.process_time_ns()-cpu)/1e6})
        # The diagnostic comparisons and output hashes are outside timed calls.
        require(actual==expected,'retained_dependency_semantics_changed:'+scope)
        require(all(item['kind']=='return' for item in expected),'retained_dependency_case_not_supported')
        checks.append({'scope':scope,'retained_lists':len(dependencies),'same_outputs':True,
                       'outputs_sha256':sha(canonical(expected))})
        for fixture in fixtures():
            left=outcome(before,fixture['raw'],fixture['request'])
            right=outcome(after,fixture['raw'],fixture['request'])
            require(right==left,'fixture_semantics_changed:'+scope+':'+fixture['name'])
            require((left['kind']=='return')==fixture['accepted'],'fixture_expected_acceptance_wrong:'+fixture['name'])
            checks.append({'scope':scope,'fixture':fixture['name'],'accepted':fixture['accepted'],
                'same_output_or_exact_error':True,'outcome_sha256':sha(canonical(left)),
                'error':{k:left[k] for k in ('type','message')} if left['kind']=='raise' else None})
    # Verify the public complete validator, not only tokenization.
    public=[]
    for label,subject in [('baseline',base),('candidate',candidate)]:
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        value=subject.validate_project_compiler(prepared['compiler_raw'],request)
        public.append({'variant':label,'wall_ms':(time.perf_counter_ns()-start)/1e6,
            'process_cpu_ms':(time.process_time_ns()-cpu)/1e6,'value':value})
    require(public[0]['value']==public[1]['value'],'complete_public_compiler_result_changed')
    public_hash=sha(canonical(public[0]['value']))
    for row in public:
        del row['value'];row['complete_output_sha256']=public_hash
    require(initial_inputs==(sha(prepared['compiler_raw']),sha(base._canonical(request))),'original_inputs_mutated')
    return {'mode':'equivalence','retained_nonempty_lists':576,'module_and_PROGRAM_compared':True,
        'checks':checks,'lexer_only_current_host_timings':timings,'public_compiler_validator_timings':public,
        'complete_public_compiler_outputs_identical':True,'original_inputs_unchanged':True,
        'producer_four_validation_sequence_executed':False,'native_or_shared_deadline_improvement_proved':False,
        'timing_limitations':'Fixed baseline-then-candidate order on this host; no randomized repeats, image comparison, analyzer execution or full qualification.'}

def producer(runner,prepared,variant):
    # Reload the verified source graph with one explicit source overlay. No
    # validator/function returns or policy fields are monkeypatched.
    finders=[f for f in sys.meta_path if isinstance(f,runner.VerifiedFinder)]
    require(len(finders)==1,'unexpected_verified_finder_count')
    sources=dict(finders[0].sources)
    if variant=='candidate':
        sources['nico/assessment_cpp_project_compiler.py']=(CANDIDATE,CANDIDATE_SHA)
    for name in list(sys.modules):
        if name=='nico' or name.startswith('nico.'):
            del sys.modules[name]
    sys.meta_path.remove(finders[0])
    package=types.ModuleType('nico');package.__path__=[];sys.modules['nico']=package
    sys.meta_path.insert(0,runner.VerifiedFinder(sources))
    from nico.assessment_cpp_project_compiler import project_compiler_request, _canonical
    from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
    from nico.assessment_cpp_static_environment import environment_request, validate_environment, bind_environment
    from nico.assessment_cpp_project_static import project_static_request
    receipt=runner.strict_json(runner.regular(runner.EVIDENCE/'raw/cpp-baseline-qualification/receipt.json'))
    ref=receipt['probe']['project_static_stage']['compiler_environment']['artifact']
    env_raw=runner.regular(runner.EVIDENCE/'raw/cpp-baseline-qualification'/runner.safe_path(ref['path']),
        runner.MAX_FILE,ref['sha256'],ref['bytes'])
    expected=runner.strict_json(runner.regular(runner.EVIDENCE/'001f-consumer/static-request.json'))
    input_before={key:sha(value if isinstance(value,bytes) else _canonical(value))
                  for key,value in prepared.items() if key in {'targets','database','snapshot','compiler_raw'}}
    steps=[]
    def measure(label,function,*args,**kwargs):
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        value=function(*args,**kwargs)
        steps.append({'label':label,'wall_ms':(time.perf_counter_ns()-start)/1e6,
                      'process_cpu_ms':(time.process_time_ns()-cpu)/1e6})
        return value
    start=time.perf_counter_ns();cpu=time.process_time_ns()
    request1=measure('initial_compiler_request',project_compiler_request,prepared['database'],prepared['targets'],
                     prepared['snapshot'],extended_budget=True)
    collection=measure('initial_compiler_collection',validate_project_compiler_collection,prepared['compiler_raw'],
                        request1,prepared['snapshot'])
    request2=measure('environment_compiler_request',project_compiler_request,prepared['database'],prepared['targets'],
                     prepared['snapshot'],extended_budget=True)
    ereq=measure('environment_request',environment_request,request2,prepared['compiler_raw'],runner.IMAGE,
                  collect_completed_compiler_failures=True,snapshot=prepared['snapshot'])
    env=measure('retained_environment_validation',validate_environment,env_raw,ereq)
    sreq=measure('static_request_and_environment_binding',project_static_request,prepared['database'],prepared['targets'],
                  prepared['snapshot'],prepared['compiler_raw'],extended_compiler_budget=True,environment=env,
                  header_provenance=True,collect_completed_compiler_failures=True)
    total={'wall_ms':(time.perf_counter_ns()-start)/1e6,'process_cpu_ms':(time.process_time_ns()-cpu)/1e6}
    # Verification serializations are outside measured producer intervals.
    require(_canonical(sreq)==_canonical(expected),'producer_request_bytes_changed')
    negatives=[]
    for label,function,values,kwargs in [
        ('changed_compiler_request_binding',validate_project_compiler_collection,
            (prepared['compiler_raw'],dict(request1,context_membership_sha256='0'*64),prepared['snapshot']),{}),
        ('changed_snapshot_binding',validate_project_compiler_collection,
            (prepared['compiler_raw'],request1,dict(prepared['snapshot'],file_population_sha256='0'*64)),{}),
        ('changed_environment_proof_binding',bind_environment,
            (dict(env,compiler_evidence_sha256='0'*64),request1,prepared['compiler_raw']),
            {'collect_completed_compiler_failures':True,'snapshot':prepared['snapshot']})]:
        value=outcome(function,*values,**kwargs)
        require(value['kind']=='raise','producer_mutation_control_accepted:'+label)
        negatives.append({'label':label,'error':value})
    input_after={key:sha(value if isinstance(value,bytes) else _canonical(value))
                  for key,value in prepared.items() if key in {'targets','database','snapshot','compiler_raw'}}
    require(input_before==input_after,'producer_input_mutation')
    require(collection['collection_complete'] is True and bool(collection['failed_contexts']),
            'genuine_compiler_failure_lost')
    return {'mode':'producer','variant':variant,'positive_sequence_total':total,'sequential_direct_intervals':steps,
        'four_positive_validation_sites_preserved_in_unchanged_producer_source':True,
        'dynamic_call_count_observed':None,'cProfile_enabled':False,
        'requests_same_as_retained':True,'static_request_sha256':sha(_canonical(sreq)),
        'compiler_collection_sha256':sha(_canonical(collection)),'environment_request_sha256':sha(_canonical(ereq)),
        'environment_model_sha256':sha(_canonical(env)),'input_digests_before':input_before,'input_digests_after':input_after,
        'negative_controls':negatives,'genuine_compiler_failure_preserved':True,
        'primary_fallback_union_or_final_collection_recomputed':False,'native_or_shared_deadline_improvement_proved':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('equivalence','producer'),default='equivalence')
    parser.add_argument('--variant',choices=('baseline','candidate'),default='candidate')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=args.output.absolute()
    require(output==output.resolve() and output.is_relative_to(HERE/'root-results') and not output.exists(),
            'new_private_root_output_required')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    forbidden=[]
    def audit(event,values):
        blocked=event.startswith('subprocess.') or event in {'os.system','os.posix_spawn','os.posix_spawnp','os.exec',
            'os.execve','os.spawn','os.spawnv','os.spawnve','pty.spawn','socket.connect','socket.getaddrinfo','urllib.Request'}
        if event=='open' and values and isinstance(values[0],(str,bytes,os.PathLike)):
            blocked=blocked or os.fsdecode(values[0]).startswith(('/work/source','/work/analysis','/workspace/work/frozen-bitcoin33'))
        if blocked:
            forbidden.append(event);raise RuntimeError('owned_pure_parser_forbidden_operation:'+event)
    sys.addaudithook(audit)
    raw=bound(RUNNER,RUNNER_SHA);bound(BASE_SOURCE,BASE_SHA);bound(CANDIDATE,CANDIDATE_SHA)
    require(importlib.util.find_spec('requests') is not None,'verified_decoder_dependency_missing')
    runner=types.ModuleType('owned_bound_static_runner');runner.__file__=str(RUNNER);sys.modules[runner.__name__]=runner
    exec(compile(raw,str(RUNNER),'exec'),runner.__dict__)
    prepared=runner.prepare(runner.parser().parse_args(['--mode','plan','--library-revision','f091']))
    require(prepared['library']['selected_library_head']==PARENT and prepared['library']['selected_library_tree']==PARENT_TREE,
            'expected_f091_parent_changed')
    result=equivalence(runner,prepared) if args.mode=='equivalence' else producer(runner,prepared,args.variant)
    require(not forbidden,'forbidden_operation_attempted')
    result.update(schema='nico.c34.private_dependency_parser_controls.v1',expected_parent=PARENT,expected_parent_tree=PARENT_TREE,
        private_candidate_path=str(CANDIDATE),private_candidate_sha256=CANDIDATE_SHA,baseline_sha256=BASE_SHA,
        source_scope='Verified3305 baseline plus publishedf091 guard and explicit private compiler parser overlay; no published candidate commit/image identity.',
        host={'python_executable':sys.executable,'python_version':sys.version,'kernel':list(os.uname())},
        no_native_or_target_execution=True,no_subprocess_or_network=True,no_source_mutation=True,
        compiled=False,tests_executed=False,full_native_qualified=False,production_qualified=False)
    payload=json.dumps(result,sort_keys=True,indent=2).encode()+b'\n';require(len(payload)<=8*1024*1024,'receipt_bound_exceeded')
    with output.open('xb') as stream:
        os.chmod(output,0o600);stream.write(payload)
    print(json.dumps({'output':str(output),'sha256':sha(payload),'mode':args.mode,'variant':args.variant,
        'qualification_credit':False,'native_execution':False,'producer_timing':result.get('positive_sequence_total')},sort_keys=True))

if __name__=='__main__':
    main()
