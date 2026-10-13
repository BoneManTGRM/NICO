"""Source and evidence contracts only: no native build or assessed execution."""
from pathlib import Path
import re

import pytest

from scripts.native_stage_counters import instrument as patch
from scripts.native_stage_counters.evidence import FIELDS, FIELDS_V3, parse_snapshots


def record(seq=1, event=1, phase=3, inner=0):
    counts = [0] * len(FIELDS)
    counts[0:4] = [phase, 2, 7, 11]
    counts[FIELDS.index('inner_visits')] = inner
    return (f'NICO_STAGE_V1 {seq} {event} {phase} 0 1234 500 1000000 ' +
            ' '.join(map(str, counts)) + '\n').encode()


def test_timeout_retains_entry_without_exit_or_completed_phase():
    evidence = parse_snapshots(b'normal diagnostic\n' + record(), timed_out=True, binary_sha256='a'*64)
    assert evidence['last_observed_snapshot']['alias'] == 11
    assert evidence['last_observed_snapshot']['event'] == 1
    assert evidence['timed_out'] is True
    assert evidence['precise_termination_hotspot_known'] is False
    assert evidence['analysis_completed'] is False
    assert evidence['qualification_claimed'] is False


def test_progress_and_exit_preserve_counts_without_promoting_success():
    evidence = parse_snapshots(record() + record(2, 0, inner=4096) + record(3, 2, inner=8192),
                               timed_out=False, binary_sha256='a'*64)
    assert evidence['last_observed_snapshot']['inner_visits'] == 8192
    assert evidence['analysis_completed'] is False


@pytest.mark.parametrize('tail', [b'NICO_STAGE_V1 2 0 3 0 456', b'NICO_STA'])
@pytest.mark.parametrize('truncated', [True, None])
def test_timeout_or_cap_partial_tail_preserves_valid_entry(tail, truncated):
    result = parse_snapshots(record() + tail, timed_out=True, binary_sha256='a'*64,
                             output_truncated=truncated)
    assert len(result['records']) == 1
    assert result['last_observed_snapshot']['event'] == 1
    assert result['incomplete_tail'] is True
    assert result['output_truncated'] is truncated
    assert not result['analysis_completed']


def test_malformed_completed_tail_still_fails_closed():
    with pytest.raises(ValueError, match='stage_record_invalid'):
        parse_snapshots(record() + b'NICO_STAGE_V1 malformed\n', timed_out=True, binary_sha256='a'*64)


@pytest.mark.parametrize('sha', [patch.ORIGINAL_BINARY_SHA256, '', 'a'*63, 'g'*64])
def test_original_or_invalid_binary_identity_rejected(sha):
    with pytest.raises(ValueError, match='distinct_identity'):
        parse_snapshots(record(), timed_out=True, binary_sha256=sha)


@pytest.mark.parametrize('raw', [b''.join(record(seq=i) for i in range(1, 130)), b'NICO_STAGE_V1 '+b'1 '*600+b'\n'])
def test_oversized_or_excess_output_rejected(raw):
    with pytest.raises(ValueError):
        parse_snapshots(raw, timed_out=True, binary_sha256='a'*64)


@pytest.mark.parametrize('raw', [b'NICO_STAGE_V1 secret\n', record().replace(b' 3 0 ', b' 9 0 ', 1),
                                 record(seq=2), record().replace(b' 500 ', b' -2 ')])
def test_invalid_or_non_numeric_snapshot_is_not_evidence(raw):
    with pytest.raises(ValueError, match='stage_record_invalid'):
        parse_snapshots(raw, timed_out=True, binary_sha256='a'*64)


def test_absent_opt_in_output_cannot_invent_active_phase():
    evidence = parse_snapshots(b'normal stderr\n', timed_out=True, binary_sha256='a'*64)
    assert evidence['records'] == [] and evidence['last_observed_snapshot'] is None


def test_header_opt_in_fixed_storage_rate_and_flush_contract():
    header = patch.HEADER.read_text()
    assert "v && v[0] == '1' && v[1] == '\\0'" in header
    assert 'std::uint64_t v[Count] = {}' in header
    assert 'SampleOperations = 4096' in header
    assert 'MaxRecords = 128' in header and 'MaxRecordBytes = 1024' in header
    assert 'IntervalMilliseconds = 1000' in header
    assert 'o.records >= MaxRecords' in header
    assert 'emit(1, phase)' in header and 'std::fflush(stderr)' in header
    assert 'CLOCKS_PER_SEC' in header and 'lane()' in header
    for forbidden in ('new ', 'std::vector', 'std::map', 'signal(', 'SIGUSR', 'Token::', 'Settings::'):
        assert forbidden not in header


def test_only_additions_roundtrip_and_reject_missing_anchor():
    raw = b'before\nanchor\nafter\n'
    changed = patch.insert(raw, b'anchor\n', b'counter();')
    assert patch.strip_instrumentation(changed) == raw
    with pytest.raises(ValueError, match='anchor_mismatch'):
        patch.insert(raw, b'absent\n', b'counter();')
    with pytest.raises(ValueError, match='anchor_mismatch'):
        patch.insert(raw * 2, b'anchor\n', b'counter();')


def test_exact_source_identity_is_required_before_any_output(tmp_path):
    source = tmp_path/'source'; (source/'lib').mkdir(parents=True)
    for name in patch.SOURCE_SHA256:
        (source/name).write_bytes(b'untrusted')
    output = tmp_path/'overlay'
    with pytest.raises(ValueError, match='source_identity_mismatch'):
        patch.create_overlay(source, output)
    assert not output.exists()
    assert all((source/n).read_bytes() == b'untrusted' for n in patch.SOURCE_SHA256)


def test_symlink_input_is_not_followed(tmp_path):
    target=tmp_path/'target'; target.write_bytes(b'bytes')
    link=tmp_path/'link'; link.symlink_to(target)
    with pytest.raises(OSError):
        patch.read_regular(link)


def test_header_counter_order_matches_evidence_contract():
    header=patch.HEADER.read_text()
    enum = re.search(r'enum Field : unsigned \{(.*?)Count\n\};', header, re.S).group(1)
    names = [n.strip() for n in enum.split(',') if n.strip()]
    snake = lambda name: re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    assert [snake(n) for n in names] == list(FIELDS_V3)


def test_full_record_budget_is_accepted_but_never_qualified():
    result = parse_snapshots(b''.join(record(seq=i) for i in range(1, 129)),
                             timed_out=True, binary_sha256='a'*64)
    assert len(result['records']) == 128 and not result['qualification_claimed']


def owned_template_source(tmp_path, monkeypatch):
    source = tmp_path/'source'; (source/'lib').mkdir(parents=True)
    raw = (b'#include "templatesimplifier.h"\n'
           b'    for (; passCount < passCountMax; ++passCount) {\n'
           b'            if (instantiated) {\n')
    raw += b"""
void TemplateSimplifier::expandTemplate()
{
    for (Token *tok3 = mTokenList.front(); tok3; tok3 = tok3 ? tok3->next() : nullptr) {
        for (; tok3; tok3 = tok3->next()) {
static bool isLowerThanLogicalAnd
bool TemplateSimplifier::matchSpecialization()
{
    for (auto it = specializations.cbegin(); it != specializations.cend(); ++it) {
        while (declToken != endToken) {
std::string TemplateSimplifier::getNewName(
bool TemplateSimplifier::simplifyTemplateInstantiations()
{
    for (const TokenAndName &instantiation : mTemplateInstantiations) {
static bool matchTemplateParameters(
void TemplateSimplifier::replaceTemplateUsage()
{
    for (Token *nameTok = mTokenList.front(); nameTok; nameTok = nameTok->next()) {
                for (auto ti = mTemplateInstantiations.cbegin(); ti != mTemplateInstantiations.cend();) {
static bool specMatch(
"""
    name = 'lib/templatesimplifier.cpp'
    (source/name).write_bytes(raw)
    monkeypatch.setattr(patch, 'SOURCE_SHA256', {name: patch.digest(raw)})
    return source, name, raw


def test_overlay_preserves_original_and_records_distinct_source_identity(tmp_path, monkeypatch):
    source, name, raw = owned_template_source(tmp_path, monkeypatch)
    output = tmp_path/'overlay'
    receipt = patch.create_overlay(source, output)
    assert (source/name).read_bytes() == raw
    assert patch.strip_instrumentation((output/name).read_bytes()) == raw
    assert receipt['members'][0]['after_sha256'] != receipt['members'][0]['before_sha256']
    assert receipt['instrumented_binary_sha256'] is None
    assert receipt['instrumented_binary_requires_new_identity'] is True
    assert not receipt['build_performed'] and not receipt['binary_equivalence_claimed']
    assert receipt['header_sha256'] == patch.digest((output/'lib/nico_stage_counters.h').read_bytes())
    saved = (output/name).read_bytes()
    with pytest.raises(FileExistsError):
        patch.create_overlay(source, output)
    assert (output/name).read_bytes() == saved and (source/name).read_bytes() == raw


def test_output_inside_source_is_rejected(tmp_path, monkeypatch):
    source, _, _ = owned_template_source(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='outside_source'):
        patch.create_overlay(source, source/'overlay')
    assert not (source/'overlay').exists()


def test_identity_matched_but_ambiguous_anchor_rejected(tmp_path, monkeypatch):
    source, name, raw = owned_template_source(tmp_path, monkeypatch)
    raw += b'#include "templatesimplifier.h"\n'
    (source/name).write_bytes(raw)
    monkeypatch.setattr(patch, 'SOURCE_SHA256', {name: patch.digest(raw)})
    with pytest.raises(ValueError, match='anchor_mismatch'):
        patch.create_overlay(source, tmp_path/'overlay')
    assert not (tmp_path/'overlay').exists()


def runtime_binding():
    from scripts.native_stage_counters import binding as b
    from scripts.native_stage_counters.build import recipe_identity
    _, recipe = recipe_identity(Path('docker/assessment-full-project-fuzz.Dockerfile'))
    overlay={'schema':'nico.cppcheck-stage-counter-overlay.v1','upstream_commit':'ac9db3069b9f90e81e126a090b99ad456e122cf8',
             'overlay_identity_sha256':b.OVERLAY_SHA256,'header_sha256':b.HEADER_SHA256,
             'original_binary_sha256':b.ORIGINAL_BINARY_SHA256,'instrumented_binary_sha256':None,
             'instrumentation_only':True,'build_performed':False,'binary_equivalence_claimed':False,
             'activation':{'environment':'NICO_CPP_STAGE_COUNTERS','exact_value':'1'},
             'members':[{'path':p,'before_sha256':b.SOURCE_SHA256[p],'after_sha256':b.AFTER_SHA256[p],
                         'semantic_bytes_restored':True} for p in sorted(b.SOURCE_SHA256)]}
    return {'schema':'nico.stage-runtime-binding.v4','record_version':3,'original_image':'sha256:'+'b'*64,'image':'sha256:'+'c'*64,
            'original_binary_sha256':b.ORIGINAL_BINARY_SHA256,'instrumented_binary_sha256':'a'*64,
            'observer_sha256':b.OBSERVER_SHA256,'original_archive_sha256':b.ARCHIVE_SHA256,'flags':b.FLAGS,
            'build_flags':b.BUILD_FLAGS,'compiler_version':'14.2.0','activation':overlay['activation'],
            'build_verified':True,'overlay':overlay,'recipe':recipe,'grouping':b.expected_grouping(),
            'candidate_patch_sha256':b.CANDIDATE_PATCH_SHA256,'candidate_source_sha256':dict(b.AFTER_SHA256)}


def test_runtime_binding_preserves_original_archive_authentication():
    from scripts.native_stage_counters import binding as b
    from scripts import native_timeout_diagnostic as d
    value=runtime_binding(); originals=dict(d.CURRENT_TOOLS)
    assert b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])==value
    d.verify_primary_runtime({'/usr/local/bin/cppcheck':value['instrumented_binary_sha256'],
                              '/opt/nico-clang-header-observer.so':b.OBSERVER_SHA256},value)
    assert d.CURRENT_TOOLS==originals and d.CURRENT_TOOLS['cppcheck']==b.ORIGINAL_BINARY_SHA256


@pytest.mark.parametrize('field', ['instrumented_binary_sha256','image','original_image','observer_sha256',
                                  'original_archive_sha256','original_binary_sha256'])
def test_substituted_identity_cannot_reuse_trusted_binding_seal(field):
    from scripts.native_stage_counters import binding as b
    value=runtime_binding(); seal=b.binding_digest(value); image=value['image']; original=value['original_image']
    value[field]='f'*64
    with pytest.raises(ValueError):b.validate_binding(value,image,seal,original)


@pytest.mark.parametrize('part', ['recipe','script','header','source','flags','compiler','original_image'])
def test_forged_provenance_rejected_even_with_recomputed_seal(part):
    from scripts.native_stage_counters import binding as b
    value=runtime_binding(); original=value['original_image']
    if part=='recipe':value.pop('recipe')
    elif part=='script':value['recipe']['instrument_script_sha256']='f'*64
    elif part=='header':value['overlay']['header_sha256']='f'*64
    elif part=='source':value['overlay']['members'][0]['before_sha256']='f'*64
    elif part=='flags':value['flags']=['--check-level=reduced']
    elif part=='compiler':value['compiler_version']='0.0.0'
    else:value['original_image']='sha256:'+'d'*64
    with pytest.raises(ValueError):b.validate_binding(value,value['image'],b.binding_digest(value),original)


@pytest.mark.parametrize('binary', ['f'*64, patch.ORIGINAL_BINARY_SHA256])
def test_observed_wrong_binary_fails_runtime_check(binary):
    from scripts import native_timeout_diagnostic as d
    value=runtime_binding()
    with pytest.raises(ValueError,match='rebuilt_tool_identity'):
        d.verify_primary_runtime({'/usr/local/bin/cppcheck':binary,
                                  '/opt/nico-clang-header-observer.so':value['observer_sha256']},value)


def test_only_exact_analyzer_command_receives_explicit_opt_in(monkeypatch):
    from scripts.native_stage_counters.binding import analyzer_environment,FLAGS
    argv=['/usr/local/bin/cppcheck','--xml','--project=/work/analysis/static-baseline/u2.json']+FLAGS
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','CPPCHECK_NICO_NATIVE_PROVENANCE':'/work/analysis/u2.trace.xml'}
    monkeypatch.setenv('NICO_CPP_STAGE_COUNTERS','1')
    assert analyzer_environment(argv,env,False,[argv])==env
    assert analyzer_environment(argv,env,True,[argv])=={**env,'NICO_CPP_STAGE_COUNTERS':'1'}
    assert 'NICO_CPP_STAGE_COUNTERS' not in env
    assert analyzer_environment(['/usr/local/bin/cppcheck','--version'],env,True,[argv])==env
    for wrong in (['/usr/bin/cppcheck']+argv[1:],argv+['--force'],['echo','owned']):
        with pytest.raises(ValueError,match='command_invalid'):analyzer_environment(wrong,env,True,[argv])
    for flag in (1,'1',None):
        with pytest.raises(ValueError,match='flag_invalid'):analyzer_environment(argv,env,flag,[argv])
    with pytest.raises(ValueError,match='ambient_key'):
        analyzer_environment(argv,{**env,'NICO_CPP_STAGE_COUNTERS':'1'},False,[argv])


def test_private_recipe_preserves_production_file_and_pinned_build(tmp_path):
    from scripts.native_stage_counters.build import prepare
    recipe=Path('docker/assessment-full-project-fuzz.Dockerfile'); original=recipe.read_bytes()
    destination=tmp_path/'Stage.Dockerfile'
    receipt=prepare(tmp_path,recipe,destination)
    assert recipe.read_bytes()==original
    text=destination.read_text()
    assert 'timeout 180s make -C /opt/tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck' in text
    assert text.index('patch_cppcheck_header_evidence.py /opt/tool-src') < text.index('python3 /opt/nico-stage-instrument.py') < text.index('timeout 180s make')
    assert patch.digest(destination.read_bytes())==receipt['diagnostic_recipe_sha256']
    assert patch.digest((tmp_path/'native-stage/nico_stage_counters.h').read_bytes())==receipt['header_sha256']
    with pytest.raises(FileExistsError):prepare(tmp_path,recipe,destination)


def test_generated_adapter_uses_only_diagnostic_environment_boundary():
    import ast,time
    from scripts import native_timeout_diagnostic as d
    command=['/usr/local/bin/cppcheck','--xml','--project=/work/analysis/static-baseline/u2.json']
    flags=['--showtime=file','--report-progress=1']
    program=ast.parse(d.primary_program(stage_counters=True,allowed_commands=[command+flags]))
    selected=[n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='analyzer_environment']
    selected += [n for n in program.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'stage_counters_enabled','stage_allowed_commands','original_run'} for t in n.targets)]
    selected += [[n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='_run'][-1]]
    calls=[];ns={'time':time,'_run':lambda *args:calls.append(args)}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'owned-env-adapter','exec'),ns)
    deadline=time.monotonic()+20; environment={'PATH':'retained'}
    ns['_run'](command,'owned',deadline,environment)
    assert calls[0]==(command+flags,'owned',deadline,{'PATH':'retained','NICO_CPP_STAGE_COUNTERS':'1'})
    assert environment=={'PATH':'retained'}


def test_isolated_paths_do_not_disable_qualification_or_change_production_collectors():
    import yaml
    full=yaml.load(Path('.github/workflows/cpp-full-project-integration.yml').read_text(),Loader=yaml.BaseLoader)
    patterns=full['on']['pull_request']['paths']
    paths=['scripts/native_timeout_diagnostic.py','tests/test_native_timeout_diagnostic.py',
           'scripts/native_stage_counters/instrument.py','scripts/native_stage_counters/evidence.py',
           'scripts/native_stage_counters/binding.py','scripts/native_stage_counters/build.py',
           'scripts/native_stage_counters/control.py','scripts/native_stage_counters/nico_stage_counters.h',
           'tests/test_native_stage_counters.py','.github/workflows/native-timeout-diagnostic.yml',
           'docs/evidence/cpp-stage-counters-local/README.md']
    for path in paths:
        for pattern in patterns:
            regex=re.escape(pattern).replace(r'\*','[^/]*')
            assert re.fullmatch(regex,path) is None
    diagnostic=Path('.github/workflows/native-timeout-diagnostic.yml').read_text()
    assert 'cpp-full-project-integration-refs/pull/1722/merge' in diagnostic
    assert 'queue: max' in diagnostic and 'cancel-in-progress: false' in diagnostic
    assert 'timeout-minutes: 55' in diagnostic and 'retention-days: 30' in diagnostic
    assert diagnostic.index('Prove analyzer opt-in') < diagnostic.index('Retrieve the immutable failed evidence') < diagnostic.index('repository: bitcoin/bitcoin')
    assert '--stage-runtime-binding-sha256' in diagnostic and '--original-image' in diagnostic
    assert 'tests/test_native_stage_counters.py' in diagnostic


def test_case_counter_retention_survives_outer_incomplete_json():
    import base64,hashlib,json
    from scripts.native_stage_counters.evidence import collect_case_snapshots
    raw=record()+b'NICO_STA'
    row={'context_id':'owned-case','execution':{'output':base64.b64encode(raw).decode(),
         'output_sha256':hashlib.sha256(raw).hexdigest(),'timed_out':True,'output_truncated':True}}
    native=(json.dumps({'diagnostic_partial_record':row})+'\n{"incomplete":').encode()
    found=collect_case_snapshots(native,{'instrumented_binary_sha256':'a'*64,'record_version':1},['owned-case','unstarted'])
    assert found[0]['snapshots']['incomplete_tail'] and len(found[0]['snapshots']['records'])==1
    assert found[1]['error']=='stage_execution_not_retained'
    row['execution']['output_sha256']='0'*64
    invalid=collect_case_snapshots(json.dumps({'diagnostic_partial_record':row}).encode(),
                                   {'instrumented_binary_sha256':'a'*64},['owned-case'])
    assert invalid[0]['error']=='stage_execution_output_binding' and invalid[0]['snapshots'] is None


@pytest.mark.parametrize('failure_point', ['create_timeout', 'create_error', 'extract_error'])
@pytest.mark.parametrize('cleanup', ['removed', 'absent', 'inspect_error', 'inspect_timeout',
                                     'remove_error', 'remove_timeout', 'foreign'])
def test_capture_failure_cleans_only_owned_container_and_preserves_failure(
        tmp_path, monkeypatch, failure_point, cleanup):
    import json
    import subprocess
    from scripts.native_stage_counters import build
    calls=[]; ownership={}; container_id='d'*64
    original=(subprocess.TimeoutExpired(['docker','create'],15) if failure_point=='create_timeout'
              else subprocess.CalledProcessError(1,['docker',failure_point],stderr=b'original failure'))

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs['timeout']==15 and kwargs['capture_output'] is True
        operation=argv[1]
        if operation=='create':
            ownership['name']=argv[argv.index('--name')+1]
            ownership['owner']=argv[argv.index('--label')+1].split('=',1)[1]
            if failure_point.startswith('create'): raise original
        elif operation=='cp':
            assert argv[2].startswith(ownership['name']+':')
            raise original
        elif operation=='inspect':
            assert argv[-1]==ownership['name']
            if cleanup=='inspect_timeout':raise subprocess.TimeoutExpired(argv,15)
            if cleanup in ('absent','inspect_error'):
                error=(f"Error: No such object: {ownership['name']}".encode()
                       if cleanup=='absent' else b'daemon unavailable')
                return subprocess.CompletedProcess(argv,1,b'',error)
            value={'Id':container_id,'Name':'/'+ownership['name'],
                   'Config':{'Labels':{'nico.stage.capture-owner':
                                      'someone-else' if cleanup=='foreign' else ownership['owner']}}}
            return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
        elif operation=='rm':
            assert argv==['docker','rm','--force',container_id]
            if cleanup=='remove_timeout':raise subprocess.TimeoutExpired(argv,15)
            if cleanup=='remove_error':raise subprocess.CalledProcessError(1,argv,stderr=b'cleanup failure')
        else:pytest.fail('Unexpected Docker operation: '+operation)
        return subprocess.CompletedProcess(argv,0,b'',b'')

    monkeypatch.setattr(build.subprocess,'run',run)
    with pytest.raises(type(original)) as caught:
        build.capture('sha256:'+'a'*64,'sha256:'+'b'*64,tmp_path/'out',tmp_path/'recipe')
    assert caught.value is original
    assert sum(call[1]=='create' for call in calls)==1
    assert sum(call[1]=='inspect' for call in calls)==1
    assert sum(call[1]=='rm' for call in calls)==int(cleanup in ('removed','remove_error','remove_timeout'))
    notes=getattr(original,'__notes__',[])
    if cleanup in ('removed','absent'):assert notes==[]
    else:assert len(notes)==1 and notes[0].startswith('diagnostic_stage_cleanup_failed: ')
    assert not (tmp_path/'out'/'binding.json').exists()


@pytest.mark.parametrize('failure', ['timeout','error'])
def test_cleanup_failure_after_successful_extraction_fails_capture(tmp_path, monkeypatch, failure):
    import json
    import subprocess
    from scripts.native_stage_counters import build
    owned={}; calls=[]; container_id='d'*64
    cleanup_error=(subprocess.TimeoutExpired(['docker','rm'],15) if failure=='timeout'
                   else subprocess.CalledProcessError(1,['docker','rm'],stderr=b'cleanup failure'))
    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs['timeout']==15
        if argv[1]=='create':
            owned['name']=argv[argv.index('--name')+1]
            owned['label']=argv[argv.index('--label')+1].split('=',1)[1]
        elif argv[1]=='cp':Path(argv[-1]).write_bytes(b'owned fixture bytes')
        elif argv[1]=='inspect':
            value={'Id':container_id,'Name':'/'+owned['name'],
                   'Config':{'Labels':{'nico.stage.capture-owner':owned['label']}}}
            return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
        elif argv[1]=='rm':
            assert argv[-1]==container_id
            raise cleanup_error
        else:pytest.fail('Unexpected Docker operation')
        return subprocess.CompletedProcess(argv,0,b'',b'')
    monkeypatch.setattr(build.subprocess,'run',run)
    with pytest.raises(type(cleanup_error)) as caught:
        build.capture('sha256:'+'a'*64,'sha256:'+'b'*64,tmp_path/'out',tmp_path/'recipe')
    assert caught.value is cleanup_error
    assert [c[1] for c in calls]==['create','cp','cp','inspect','rm']
    assert not (tmp_path/'out'/'binding.json').exists()


@pytest.mark.parametrize('changed', ['name','id','label'])
def test_cleanup_never_removes_unverified_container(monkeypatch, changed):
    import json
    import subprocess
    from scripts.native_stage_counters import build
    value={'Id':'a'*64,'Name':'/owned','Config':{'Labels':{'nico.stage.capture-owner':'token'}}}
    if changed=='name':value['Name']='/other'
    elif changed=='id':value['Id']='ambiguous-prefix'
    else:value['Config']['Labels']={}
    calls=[]
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
    monkeypatch.setattr(build.subprocess,'run',run)
    with pytest.raises(ValueError,match='ownership_mismatch'):
        build.cleanup_capture_container('owned','token')
    assert len(calls)==1 and calls[0][1]=='inspect'


@pytest.mark.parametrize('part', ['old_schema','old_binary','local_ungrouped_counters','local_grouping_binary',
                                  'grouping_missing','grouping_before','grouping_after',
                                  'combined_source','combined_overlay','group_script','candidate_patch'])
def test_grouped_binding_rejects_stale_or_substituted_composition(part):
    from scripts.native_stage_counters import binding as b
    value=runtime_binding()
    if part=='old_schema': value['schema']='nico.stage-runtime-binding.v1'
    elif part=='old_binary': value['instrumented_binary_sha256']=b.PRE_GROUPING_BINARY_SHA256
    elif part=='local_ungrouped_counters': value['instrumented_binary_sha256']='ed79c96b90b246110b696290e580b555ffdc7438c6f6b878adc0bee48e9911c7'
    elif part=='local_grouping_binary': value['instrumented_binary_sha256']=b.LOCAL_UNINSTRUMENTED_BINARY_SHA256
    elif part=='grouping_missing': value.pop('grouping')
    elif part=='grouping_before': value['grouping']['input_sha256']['lib/token.cpp']='0'*64
    elif part=='grouping_after': value['grouping']['output_sha256']='0'*64
    elif part=='combined_source': value['candidate_source_sha256']['lib/templatesimplifier.cpp']='0'*64
    elif part=='combined_overlay': value['overlay']['overlay_identity_sha256']='4c82ebc973709634ad378c98ce0fd0c7fdfe4a73726b48503967de3c60319607'
    elif part=='group_script': value['recipe']['grouping_script_sha256']='0'*64
    else: value['candidate_patch_sha256']='0'*64
    with pytest.raises(ValueError):
        b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])


def test_grouping_order_and_exact_script_are_bound(tmp_path):
    from scripts.native_stage_counters import build, binding as b, specialization_groups as groups
    recipe=Path('docker/assessment-full-project-fuzz.Dockerfile')
    updated, receipt=build.recipe_identity(recipe)
    assert patch.digest(Path(groups.__file__).read_bytes())==b.GROUP_SCRIPT_SHA256
    assert receipt['candidate_patch_sha256']==b.CANDIDATE_PATCH_SHA256
    assert updated.index('patch_cppcheck_header_evidence.py /opt/tool-src') < updated.index('python3 /opt/nico-specialization-groups.py') < updated.index('python3 /opt/nico-stage-instrument.py') < updated.index('timeout 180s make')
    assert b.SOURCE_SHA256['lib/templatesimplifier.cpp']==b.expected_grouping()['output_sha256']
    # Neither order can silently apply to the other's output.
    with pytest.raises(ValueError,match='source_identity_mismatch'):
        patch.instrument('lib/templatesimplifier.cpp', b'old or altered source')
    with pytest.raises(ValueError,match='source_identity'):
        groups.transform(b'counter-modified source')


def test_real_owned_verdict_requires_every_exact_case_and_existing_todos():
    from scripts.native_stage_counters import owned_regressions as owned
    names=owned.expected_names()
    assert len(names)==253 and len(set(names))==253
    assert names[:3]==['TestSimplifyTemplate::nicoGroupingRealDeclarationCallbacks',
                      'TestSimplifyTemplate::nicoGroupingRealCopyUnregister',
                      'TestSimplifyTemplate::nicoGroupingRepeatedExpansion']
    stdout='\n'.join(names)+'\nNumber of tests: 253\nNumber of todos: 12\n'
    stderr='Tests failed: 0\n'
    execution={'exit_code':0,'timed_out':False}
    assert owned.verdict(stdout,stderr,execution)['passed']
    for changed in (stdout.replace(names[3]+'\n',''),stdout+names[3]+'\n',
                    stdout.replace('253','0'),stdout.replace('todos: 12','todos: 11'),
                    stdout.replace(names[3],names[3]+'not-real')):
        assert not owned.verdict(changed,stderr,execution)['passed']
    assert not owned.verdict(stdout,'Tests failed: 1\n',execution)['passed']
    assert not owned.verdict(stdout,stderr,{'exit_code':1,'timed_out':False})['passed']
    assert not owned.verdict(stdout,stderr,{'exit_code':0,'timed_out':True})['passed']


def test_owned_harness_retains_failed_build_and_does_not_start_tests(tmp_path,monkeypatch,owned_tool_identities):
    from scripts.native_stage_counters import owned_regressions as owned
    source=tmp_path/'source';(source/'lib').mkdir(parents=True);(source/'test').mkdir()
    raw=b'owned source'
    for name in owned.AFTER_SHA256: (source/name).write_bytes(raw)
    (source/'lib/nico_stage_counters.h').write_bytes(raw)
    (source/'test/testsimplifytemplate.cpp').write_bytes(raw)
    monkeypatch.setattr(owned,'AFTER_SHA256',{n:owned.digest(raw) for n in owned.AFTER_SHA256})
    monkeypatch.setattr(owned,'HEADER_SHA256',owned.digest(raw))
    monkeypatch.setattr(owned,'PRODUCTION_SOURCE_SHA256',{})
    monkeypatch.setattr(owned,'apply_fixture',lambda *args:raw)
    calls=[]
    def phase(source,output,name,argv,seconds):
        calls.append((name,seconds))
        return {'exit_code':2,'timed_out':False,'error':None}
    monkeypatch.setattr(owned,'run_phase',phase)
    result=owned.run(source,tmp_path/'out')
    assert not result['passed'] and len(result['tests_not_run'])==253
    assert calls==[('build',300)] and (tmp_path/'out/result.json').is_file()


def test_owned_patch_identity_checked_before_source_application():
    from scripts.native_stage_counters import owned_regressions as owned
    with pytest.raises(ValueError,match='input_identity'):
        owned.apply_fixture(b'unreviewed', (owned.ROOT/'owned-fixtures.patch').read_bytes())
    assert patch.digest((owned.ROOT/'owned-fixtures.patch').read_bytes())==owned.PATCH_SHA256


def test_owned_phase_cleans_descendants_even_when_parent_exits_on_term(tmp_path,monkeypatch):
    from scripts.native_stage_counters import owned_regressions as owned
    import subprocess,signal
    waits=[];signals=[];environments=[]
    class Process:
        pid=123456
        def wait(self,timeout):
            waits.append(timeout)
            if len(waits)==1: raise subprocess.TimeoutExpired(['owned'],timeout)
            return -signal.SIGTERM
    def popen(argv,**kwargs):
        environments.append(kwargs['env']);return Process()
    monkeypatch.setattr(owned.subprocess,'Popen',popen)
    monkeypatch.setattr(owned.os,'killpg',lambda pid,sig:signals.append((pid,sig)))
    monkeypatch.setenv('MAKEFLAGS','-n')
    receipt=owned.run_phase(tmp_path,tmp_path,'owned',['not-executed'],10)
    assert receipt['timed_out'] and receipt['cleanup']=='remaining_group_killed'
    assert signals==[(123456,signal.SIGTERM),(123456,signal.SIGKILL)]
    assert 'MAKEFLAGS' not in environments[0] and 'NICO_CPP_STAGE_COUNTERS' not in environments[0]
    assert (tmp_path/'owned.json').is_file()


def test_owned_phase_start_failure_is_retained(tmp_path,monkeypatch):
    from scripts.native_stage_counters import owned_regressions as owned
    def popen(*args,**kwargs):raise PermissionError('owned denied')
    monkeypatch.setattr(owned.subprocess,'Popen',popen)
    receipt=owned.run_phase(tmp_path,tmp_path,'owned',['not-executed'],10)
    assert receipt['exit_code'] is None and receipt['error']=='PermissionError: owned denied'
    assert (tmp_path/'owned.json').is_file()


def test_owned_harness_refuses_stale_objects_before_build(tmp_path,owned_tool_identities):
    from scripts.native_stage_counters import owned_regressions as owned
    source=tmp_path/'source';source.mkdir();(source/'stale.o').write_bytes(b'old')
    with pytest.raises(ValueError,match='clean_build_required'):
        owned.run(source,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_owned_successful_build_without_binary_is_retained_as_failure(tmp_path,monkeypatch,owned_tool_identities):
    from scripts.native_stage_counters import owned_regressions as owned
    source=tmp_path/'source';(source/'lib').mkdir(parents=True);(source/'test').mkdir()
    raw=b'owned source';(source/'lib/nico_stage_counters.h').write_bytes(raw)
    (source/'test/testsimplifytemplate.cpp').write_bytes(raw)
    monkeypatch.setattr(owned,'AFTER_SHA256',{})
    monkeypatch.setattr(owned,'PRODUCTION_SOURCE_SHA256',{})
    monkeypatch.setattr(owned,'HEADER_SHA256',owned.digest(raw))
    monkeypatch.setattr(owned,'apply_fixture',lambda *args:raw)
    monkeypatch.setattr(owned,'run_phase',lambda *args:{'exit_code':0,'timed_out':False,'error':None})
    result=owned.run(source,tmp_path/'out')
    assert not result['passed'] and result['error'].startswith('FileNotFoundError:')
    assert len(result['tests_not_run'])==253 and (tmp_path/'out/result.json').is_file()


@pytest.fixture
def owned_tool_identities(tmp_path,monkeypatch):
    # Pure Python harness tests must not depend on CI having the native compiler.
    from scripts.native_stage_counters import owned_regressions as owned
    executable=tmp_path/'owned-tool'; executable.write_bytes(b'owned, never executed')
    for name in ('COMPILER','MAKE'):
        monkeypatch.setattr(owned,name,executable)
        monkeypatch.setattr(owned,name+'_SHA256',owned.digest(executable.read_bytes()))
