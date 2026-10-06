"""Per-context Cppcheck evidence over the existing immutable project inputs.

Compiler/header qualification is a prerequisite, not static-analysis evidence.
Singleton databases prevent repeated configurations of one file being merged.
This opt-in stage does not activate a production worker or approve findings.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import stat
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

from nico.assessment_cpp_compiler_evidence import _source_path, safe_compile_argv, _regular_bytes, _run
from nico.assessment_cpp_generated_context import _project_option, _stable_bytes
from nico.assessment_cpp_project_compiler import (
    _canonical, _digest, _extra_option, _syntax_argv, _verify_input,
    project_compiler_request, validate_project_compiler, GENERATED_FILE_LIMIT,
)

from nico.assessment_cpp_static_environment import (analyzer_environment_arguments,
    STATIC_ENV_SUPPORT, verify_environment_inputs, context_dependencies,
    modeled_missing_include, bind_environment)
from nico.assessment_cpp_header_evidence import (HEADER_SCHEMA, HEADER_TOOL_MANIFEST_SHA256,
    HEADER_APPLIER_SHA256, _require, validate_header_trace, validate_header_tool_receipt)

TOOL_VERSION = '2.17.1'
CHECKS = 'warning,style,performance,portability,information,missingInclude'
LIMITS = {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
# Phase maxima share the existing aggregate deadline; they are not additive
# allowances. Every command, retention and validation remains deadline-fenced.
STAGE_BUDGET = {'schema': 'nico.cpp-static-combined-budget.v3',
    'primary_seconds': 540, 'fallback_seconds': 480, 'controller_seconds': 300,
    'shared_execution_seconds': 1020, 'limits_share_execution_envelope': True}
STAGE_EXECUTION_SECONDS = STAGE_BUDGET['shared_execution_seconds']
STAGE_WALL_SECONDS = STAGE_EXECUTION_SECONDS + 10
STREAM_LIMIT = 48 * 1024 * 1024
REQUEST_LIMIT = 16 * 1024 * 1024
XML_LIMIT = 1024 * 1024
XML_COMPRESSED_LIMIT = 2 * 1024 * 1024


def _encode_xml(raw, *, compact=False):
    """Encode bounded native XML while preserving the digest of raw tool bytes."""
    if not isinstance(raw, bytes) or len(raw) > XML_LIMIT:
        raise ValueError('worker_project_static_xml_limit')
    if not raw:
        return '', None, 'zlib' if compact else 'identity'
    stored = zlib.compress(raw, 9) if compact else raw
    if len(stored) > XML_COMPRESSED_LIMIT:
        raise ValueError('worker_project_static_xml_limit')
    return base64.b64encode(stored).decode('ascii'), _digest(raw), 'zlib' if compact else 'identity'


def _decode_xml(value, digest, encoding='identity'):
    """Decode retained XML with a hard uncompressed bound."""
    if not isinstance(value, str) or encoding not in {'identity', 'zlib'}:
        raise ValueError('worker_project_static_xml_digest')
    try:
        stored = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('worker_project_static_xml_digest') from exc
    if len(stored) > XML_COMPRESSED_LIMIT:
        raise ValueError('worker_project_static_xml_digest')
    if not stored:
        if digest is not None:
            raise ValueError('worker_project_static_xml_digest')
        return b''
    try:
        if encoding == 'zlib':
            inflater = zlib.decompressobj()
            raw = inflater.decompress(stored, XML_LIMIT + 1)
            if (len(raw) > XML_LIMIT or inflater.unconsumed_tail or inflater.unused_data
                    or not inflater.eof):
                raise ValueError('worker_project_static_xml_digest')
        else:
            raw = stored
    except zlib.error as exc:
        raise ValueError('worker_project_static_xml_digest') from exc
    if len(raw) > XML_LIMIT or not isinstance(digest, str) or _digest(raw) != digest:
        raise ValueError('worker_project_static_xml_digest')
    return raw


def _static_plan(context, environment=None, *, header_provenance=False):
    """Preserve supported imported arguments, never execute a database command.

    Pinned ImportProject supports -D/-U/-I/-isystem/-std and selected scalar
    flags, but not GCC forced/quote-only include semantics. Reject these rather
    than silently remove them. Compiler built-in macro equivalence is not
    established by this analyzer model.
    """
    args = context['invocation']
    if any(a in {'-iquote', '-include', '-imacros'} for a in args):
        raise ValueError('worker_project_static_include_model_unsupported')
    defines = set()
    for arg in args:
        if arg.startswith(('-D', '-U')):
            name = arg[2:].split('=', 1)[0]
            if name in defines and not header_provenance:
                raise ValueError('worker_project_static_macro_model_ambiguous')
            defines.add(name)
    environment_flags = []
    if environment is not None:
        args, environment_flags = analyzer_environment_arguments(context, environment)
    if header_provenance:
        environment_flags = ['--std=' + _header_standard(context, environment), *environment_flags]
        # ImportProject stores -U in a set and cannot model interleaved D/U.
        # The original argv and executed GCC macro query remain bound above.
        # For this new analyzer contract retain each macro's final operation,
        # in its original relative order; never change the compiler database.
        args=_analyzer_macro_arguments(args)
    stem = '/work/analysis/static-baseline/u' + str(context['index'])
    database = _canonical([{'directory': '/work/analysis',
        'file': context['analysis_file'], 'arguments': list(args)}]).decode()
    argv = ['/usr/local/bin/cppcheck', '--xml', '--enable=' + CHECKS,
        '--check-level=exhaustive', '--max-configs=1', '--platform=unix64', '-j1',
        '--project=' + stem + '.json', '--output-file=' + stem + '.xml', *environment_flags]
    return database, argv


def _analyzer_macro_arguments(args):
    last={arg[2:].split('=',1)[0]:i for i,arg in enumerate(args) if arg.startswith(('-D','-U'))}
    # ImportProject synthesizes PIC/PIE macros with its own scalar values.
    # For v3 use the bound actual compiler predefines for those codegen flags.
    return [arg for i,arg in enumerate(args) if arg not in {'-fPIC','-fpic','-fPIE','-fpie'}
        and (not arg.startswith(('-D','-U')) or last[arg[2:].split('=',1)[0]]==i)]


def _header_standard(context, environment):
    if not isinstance(environment,dict):
        raise ValueError('worker_project_static_header_environment_missing')
    member = environment['contexts'][context['context_id']]
    standard = environment['queries'][member['query']].get('language_standard')
    if standard not in {'c89','c99','c11','c17','c23','c++03','c++11','c++14','c++17','c++20','c++23','c++26'}:
        raise ValueError('worker_project_static_header_standard_unproven')
    return standard


def _header_effective_inputs(context):
    """Pinned ImportProject/fsSetIncludePaths + createDUI input semantics."""
    imported=json.loads(context['analyzer_database'])[0]['arguments']
    paths,undefined=[],set();index=1
    while index<len(imported):
        arg=imported[index];index+=1
        if arg=='-I':
            if index>=len(imported):raise ValueError('worker_project_static_include_invalid')
            path=imported[index];index+=1
        elif arg.startswith('-I'):path=arg[2:]
        elif arg.startswith('-U'):
            undefined.add(arg[2:]);continue
        else:continue
        if not path.startswith('/'):raise ValueError('worker_project_static_include_invalid')
        if path not in paths:paths.append(path)
    forced=[arg[len('--include='):] for arg in context['analyzer_invocation'] if arg.startswith('--include=')]
    if len(forced)!=1:raise ValueError('worker_project_static_header_predefines_invalid')
    return {'undef':sorted(undefined),'include_path':[path if path.endswith('/') else path+'/' for path in paths],
        'forced_input':forced}


def project_static_request(database, targets, snapshot, compiler_raw, *, extended_compiler_budget=None, environment=None, header_provenance=False, collect_completed_compiler_failures=False):
    if type(header_provenance) is not bool or type(collect_completed_compiler_failures) is not bool:
        raise ValueError('worker_project_static_header_flag_invalid')
    """Reconstruct every binding; require completed native compiler evidence."""
    from nico.assessment_cpp_full_project import _json
    # Retained-evidence callers may reconstruct either version. Live callers
    # supply their selected policy so evidence cannot choose a different one.
    if extended_compiler_budget is None:
        compiler_schema = _json(compiler_raw).get('schema')
        extended_compiler_budget = compiler_schema == 'nico.cpp-project-compiler-evidence.v2'
    compiler_request = project_compiler_request(database, targets, snapshot,
        extended_budget=extended_compiler_budget)
    collection = None
    if collect_completed_compiler_failures:
        from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
        # Collection already runs the full compiler validator and binds the
        # snapshot. Avoid a second parse whose result is unused in this path.
        collection = validate_project_compiler_collection(compiler_raw, compiler_request, snapshot)
    elif not validate_project_compiler(compiler_raw, compiler_request)['complete']:
        raise ValueError('worker_project_static_compiler_incomplete')
    records = _json(compiler_raw)['records']
    if environment is not None:
        bind_environment(environment, compiler_request, compiler_raw,
            collect_completed_compiler_failures=collect_completed_compiler_failures, snapshot=snapshot)
    contexts = []
    for context, record in zip(compiler_request['contexts'], records):
        data, argv = _static_plan(context, environment, header_provenance=header_provenance)
        contexts.append({**context, 'analyzer_database': data,
            'analyzer_database_sha256': _digest(data.encode()), 'analyzer_invocation': argv,
            'source_dependencies': record['source_dependencies'],
            'generated_dependencies': record['generated_dependencies']})
    request = {'schema': 'nico.cpp-project-static-request.v1', 'tool_version': TOOL_VERSION,
        'database_sha256': compiler_request['database_sha256'],
        'context_membership_sha256': compiler_request['context_membership_sha256'],
        'snapshot_population_sha256': compiler_request['snapshot_population_sha256'],
        'compiler_evidence_sha256': _digest(compiler_raw),
        'targets': dict(targets), 'generated_files': compiler_request['generated_files'],
        'contexts': contexts, 'limits': dict(LIMITS)}
    if environment is not None:
        request.update(schema='nico.cpp-project-static-request.v2', compiler_environment=environment)
    if header_provenance:
        request.update(schema='nico.cpp-project-static-request.v3',
            header_trace_schema=HEADER_SCHEMA, header_tool_manifest_sha256=HEADER_TOOL_MANIFEST_SHA256)
    if collection is not None:
        if not (header_provenance and environment is not None):
            raise ValueError('worker_project_static_compiler_collection_policy_invalid')
        from nico.assessment_cpp_compiler_collection import collection_summary
        request.update(schema='nico.cpp-project-static-request.v4',
                       compiler_collection=collection_summary(collection))
    if len(_canonical(request)) > REQUEST_LIMIT:
        raise ValueError('worker_project_static_request_limit')
    return request


def collect_project_static(request):
    """Run pinned Cppcheck inside the existing private analyst UID only."""
    import resource
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_project_static_identity')
    if (not isinstance(request, dict) or request.get('schema') not in {'nico.cpp-project-static-request.v1', 'nico.cpp-project-static-request.v2', 'nico.cpp-project-static-request.v3', 'nico.cpp-project-static-request.v4'}
            or request.get('tool_version') != TOOL_VERSION or request.get('limits') != LIMITS
            or not isinstance(request.get('contexts'), list) or not 1 <= len(request['contexts']) <= 20000):
        raise ValueError('worker_project_static_request_invalid')
    environment_model = request.get('compiler_environment')
    header_provenance = request['schema'].endswith(('.v3','.v4'))
    if (request['schema'].endswith(('.v2','.v3','.v4'))) != (environment_model is not None):
        raise ValueError('worker_project_static_environment_missing')
    if environment_model is not None:
        verify_environment_inputs(environment_model)
    header_tool_raw = None
    if header_provenance:
        if (request.get('header_trace_schema')!=HEADER_SCHEMA
                or request.get('header_tool_manifest_sha256')!=HEADER_TOOL_MANIFEST_SHA256):
            raise ValueError('worker_project_static_header_contract_invalid')
        header_tool_raw = _regular_bytes('/opt/nico-cppcheck-header-observer.json',65536)
        validate_header_tool_receipt(header_tool_raw)
    parent = Path('/work/analysis')
    info = parent.lstat()
    if (parent.resolve(strict=True) != parent or info.st_uid != 1001
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('worker_project_static_private_directory_invalid')
    directory = parent / 'static-baseline'
    directory.mkdir(mode=0o700)
    for index, context in enumerate(request['contexts']):
        args, source = _syntax_argv(context, request['generated_files'])
        data, argv = _static_plan(context, environment_model, header_provenance=header_provenance)
        if (context['index'] != index or args != context['invocation'] or source != context['analysis_file']
                or data != context['analyzer_database'] or _digest(data.encode()) != context['analyzer_database_sha256']
                or argv != context['analyzer_invocation']):
            raise ValueError('worker_project_static_plan_mismatch')
    resource.setrlimit(resource.RLIMIT_FSIZE, (XML_LIMIT, XML_LIMIT))
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
        'HOME': str(directory), 'TMPDIR': str(directory), 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
    start = time.monotonic()
    deadline = start + LIMITS['wall_seconds']
    version = _run(['/usr/local/bin/cppcheck', '--version'], str(directory / 'version'),
                   min(deadline, start + 5), environment)
    tool_ok = (version['exit_code'] == 0 and not version['timed_out'] and not version['output_truncated']
               and base64.b64decode(version['output'], validate=True).strip() == ('Cppcheck ' + TOOL_VERSION).encode())

    def one(context):
        record = {'context_id': context['context_id'], 'invocation': context['analyzer_invocation'],
            'database_sha256': context['analyzer_database_sha256'], 'execution': None,
            'xml': '', 'xml_sha256': None, 'error': None}
        if environment_model is not None:
            record['xml_encoding'] = 'zlib'
        if header_provenance:
            record.update(header_trace='',header_trace_sha256=None,header_trace_encoding='zlib')
        try:
            if not tool_ok:
                raise ValueError('worker_project_static_tool_version')
            if time.monotonic() >= deadline:
                raise ValueError('worker_project_static_deadline')
            # A captured failed compiler context has no dependency credit.
            # Independently verify its declared main input before the analyzer
            # reads it; this grants no compiler/header inclusion coverage.
            if request['schema'].endswith('.v4'):
                if context['origin'] == 'original':
                    _verify_input('/work/source', context['path'], request['targets'][context['path']])
                else:
                    item = request['generated_files'][context['path']]
                    _verify_input('/work/analysis/generated-baseline', context['path'],
                        item['sha256'], item['bytes'], True)
            for path, sha in context['source_dependencies'].items():
                _verify_input('/work/source', path, sha)
            for path, sha in context['generated_dependencies'].items():
                _verify_input('/work/analysis/generated-baseline', path, sha,
                              request['generated_files'][path]['bytes'], True)
            stem = str(directory / ('u' + str(context['index'])))
            path = Path(stem + '.json')
            with path.open('xb') as handle:
                handle.write(context['analyzer_database'].encode())
            path.chmod(0o444)
            native_environment = dict(environment)
            if header_provenance:
                trace_path = Path(stem+'.trace.xml')
                descriptor=os.open(trace_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                os.close(descriptor)
                native_environment['CPPCHECK_NICO_NATIVE_PROVENANCE']=str(trace_path)
            record['execution'] = _run(context['analyzer_invocation'], stem,
                min(deadline, time.monotonic() + LIMITS['case_seconds']), native_environment)
            # Retain even failing native XML; the controller decides completeness.
            xml = _regular_bytes(stem + '.xml', XML_LIMIT)
            encoded, digest, encoding = _encode_xml(xml, compact=environment_model is not None)
            record.update(xml=encoded, xml_sha256=digest)
            if environment_model is not None:
                record['xml_encoding'] = encoding
            if header_provenance:
                traced=_regular_bytes(str(trace_path),XML_LIMIT)
                encoded,digest,encoding=_encode_xml(traced,compact=True)
                record.update(header_trace=encoded,header_trace_sha256=digest,header_trace_encoding=encoding)
            if _regular_bytes(stem + '.json', REQUEST_LIMIT) != context['analyzer_database'].encode():
                raise ValueError('worker_project_static_database_changed')
        except (ValueError, OSError, KeyError, TypeError) as exc:
            code = str(exc)
            record['error'] = code if re.fullmatch(r'worker_project_static_[a-z_]+', code) else 'worker_project_static_unavailable'
        return record

    with ThreadPoolExecutor(max_workers=LIMITS['parallel']) as pool:
        records = list(pool.map(one, request['contexts']))
    if environment_model is not None:
        verify_environment_inputs(environment_model)
    result = {'schema': request['schema'].replace('-request.', '-evidence.'), 'request_sha256': _digest(_canonical(request)),
        'analyst_uid': os.getuid(), 'version': version, 'records': records,
        'duration_ms': int((time.monotonic() - start) * 1000)}
    if header_provenance:
        result.update(header_tool_receipt=base64.b64encode(header_tool_raw).decode(),
            header_tool_receipt_sha256=_digest(header_tool_raw))
    if len(_canonical(result)) > STREAM_LIMIT:
        raise ValueError('worker_project_static_output_limit')
    return result


def _execution(value, maximum):
    from nico.assessment_cpp_configuration import decode_stream
    if (not isinstance(value, dict) or set(value) != {'exit_code', 'timed_out', 'output_truncated',
            'duration_ms', 'output', 'output_sha256'}
            or type(value['exit_code']) is not int or not -255 <= value['exit_code'] <= 255
            or any(type(value[k]) is not bool for k in ('timed_out', 'output_truncated'))
            or type(value['duration_ms']) is not int or not 0 <= value['duration_ms'] <= maximum):
        raise ValueError('worker_project_static_execution_invalid')
    raw = decode_stream(value['output'])
    if len(raw) > 65536 or _digest(raw) != value['output_sha256']:
        raise ValueError('worker_project_static_execution_digest')
    return value['exit_code'] == 0 and not value['timed_out'] and not value['output_truncated'], raw


def validate_project_static(raw, request):
    """Reconstruct context completion and findings from bounded native output."""
    from xml.etree import ElementTree as ET
    from nico.assessment_cpp_full_project import _json
    from nico.assessment_cpp_configuration import decode_stream
    from nico.cppcheck_native_output import parse_native
    if not isinstance(raw, bytes) or not 0 < len(raw) <= STREAM_LIMIT:
        raise ValueError('worker_project_static_output_limit')
    evidence = _json(raw)
    native_evidence_sha256 = _digest(raw)
    fields = {'schema', 'request_sha256', 'analyst_uid', 'version', 'records', 'duration_ms'}
    header_provenance = request['schema'].endswith(('.v3','.v4'))
    if header_provenance:
        fields |= {'header_tool_receipt','header_tool_receipt_sha256'}
    if (not isinstance(evidence, dict) or set(evidence) != fields
            or evidence['schema'] != request['schema'].replace('-request.', '-evidence.')
            or evidence['request_sha256'] != _digest(_canonical(request))
            or type(evidence['analyst_uid']) is not int or evidence['analyst_uid'] != 1001
            or type(evidence['duration_ms']) is not int or not 0 <= evidence['duration_ms'] <= 543000
            or not isinstance(evidence['records'], list) or len(evidence['records']) != len(request['contexts'])):
        raise ValueError('worker_project_static_evidence_invalid')
    if header_provenance:
        try:
            receipt=base64.b64decode(evidence['header_tool_receipt'],validate=True)
        except (TypeError,ValueError) as error:
            raise ValueError('worker_project_static_header_tool_invalid') from error
        if _digest(receipt)!=evidence['header_tool_receipt_sha256']:
            raise ValueError('worker_project_static_header_tool_invalid')
        validate_header_tool_receipt(receipt)
    version_ok, version = _execution(evidence['version'], 8000)
    if not version_ok or version.strip() != ('Cppcheck ' + TOOL_VERSION).encode():
        raise ValueError('worker_project_static_tool_version')
    attempted, analyzed, findings, limitations, modeled_inputs, header_contexts = [], [], [], [], [], []
    environment_model = request.get('compiler_environment')
    duration = evidence['version']['duration_ms']
    legacy_fields = {'context_id', 'invocation', 'database_sha256', 'execution', 'xml', 'xml_sha256', 'error'}
    compact_fields = legacy_fields | {'xml_encoding'}
    for context, row in zip(request['contexts'], evidence['records']):
        expected_fields = compact_fields if 'xml_encoding' in row else legacy_fields
        if header_provenance:
            expected_fields |= {'header_trace','header_trace_sha256','header_trace_encoding'}
        if (not isinstance(row, dict) or set(row) != expected_fields or row['context_id'] != context['context_id']
                or row['invocation'] != context['analyzer_invocation']
                or row['database_sha256'] != context['analyzer_database_sha256']
                or row['error'] is not None and (not isinstance(row['error'], str)
                    or re.fullmatch(r'worker_project_static_[a-z_]+', row['error']) is None)):
            raise ValueError('worker_project_static_record_invalid')
        xml = _decode_xml(row['xml'], row['xml_sha256'], row.get('xml_encoding', 'identity'))
        header_trace = (_decode_xml(row['header_trace'],row['header_trace_sha256'],row['header_trace_encoding'])
            if header_provenance else None)
        if row['execution'] is None:
            if row['error'] is None or xml or header_trace:
                raise ValueError('worker_project_static_missing_execution')
            limitations.append({'context_id': context['context_id'], 'rule_id': row['error']})
            continue
        success, progress = _execution(row['execution'], 93000)
        attempted.append(context['context_id'])
        duration += row['execution']['duration_ms']
        if not success or row['error']:
            limitations.append({'context_id': context['context_id'],
                'rule_id': row['error'] or 'native_execution_incomplete'})
            continue
        try:
            xml_text = xml.decode('utf-8', 'strict')
        except UnicodeError as error:
            raise ValueError('worker_project_static_xml_invalid') from error
        # Match the pinned producer's UTF-8 output before the parser can
        # auto-detect another encoding and process prohibited declarations.
        if not xml or '\x00' in xml_text or '<!DOCTYPE' in xml_text.upper() or '<!ENTITY' in xml_text.upper():
            raise ValueError('worker_project_static_xml_invalid')
        locations = {'/work/source/' + p: ('original', p, sha)
                     for p, sha in context['source_dependencies'].items()}
        locations.update({'/work/analysis/generated-baseline/' + p: ('generated', p, sha)
                          for p, sha in context['generated_dependencies'].items()})
        if request['schema'].endswith('.v4'):
            origin, path = context['origin'], context['path']
            source_sha = (request['targets'][path] if origin == 'original'
                          else request['generated_files'][path]['sha256'])
            locations[context['analysis_file']] = (origin, path, source_sha)
        if environment_model is not None:
            dependencies = context_dependencies(environment_model, context['context_id'])
            locations.update({row['projection']: ('toolchain', path, row['sha256'])
                              for path, row in dependencies.items() if row['projection']})
            query = environment_model['queries'][environment_model['contexts'][context['context_id']]['query']]
            locations[query['predefines_path']] = ('compiler_predefines', query['predefines_path'], query['predefines_sha256'])
        if header_provenance:
            if not header_trace:
                raise ValueError('worker_project_static_header_trace_missing')
            # Inventory remains complete even when a file was not a compiler
            # dependency. This does not credit that file as included or parsed.
            header_locations = dict(locations)
            header_locations.update({'/work/source/'+p:('original',p,sha) for p,sha in request['targets'].items()})
            header_locations.update({'/work/analysis/generated-baseline/'+p:('generated',p,value['sha256'])
                for p,value in request['generated_files'].items()})
            definitions={}
            for arg in context['invocation']:
                if arg.startswith('-D'):
                    name,separator,value=arg[2:].partition('=');definitions[name]=value if separator else '1'
                elif arg.startswith('-U'):
                    definitions.pop(arg[2:],None)
            header=validate_header_trace(header_trace,source=context['analysis_file'],locations=header_locations,
                standard=_header_standard(context,environment_model),configuration_defines=definitions,
                effective_inputs=_header_effective_inputs(context))
            header_contexts.append({'context_id':context['context_id'],
                **{key:value for key,value in header.items() if key!='inventoried_files'}})
        try:
            document = ET.fromstring(xml)
            # Unknown diagnostic locations are retained raw but cannot become
            # source-bound findings or a completed context. Parse once and pass
            # the same verified tree into the native adapter.
            for loc in document.findall('errors/error/location'):
                if loc.get('file') not in locations:
                    raise ValueError('worker_project_static_location_unbound')
            native_findings, limits, observed = parse_native(xml_text, progress.decode('utf-8'),
                sorted(locations), version=TOOL_VERSION, document=document)
        except (ET.ParseError, UnicodeError) as exc:
            raise ValueError('worker_project_static_xml_invalid') from exc
        if environment_model is not None:
            modeled_index = {}
            for path, member in dependencies.items():
                if member['modeled_name'] and member['model']:
                    modeled_index.setdefault((member['modeled_name'], member['model']), []).append(path)
            execution_limits = []
            for entry in limits:
                modeled = modeled_missing_include(entry, environment_model, context['context_id'],
                    dependencies, modeled_index)
                if modeled:
                    modeled_inputs.append({**modeled, 'native_evidence_sha256': native_evidence_sha256})
                else:
                    execution_limits.append(entry)
            limits = execution_limits
            if not any(entry['rule_id'] == 'checkersReport' for entry in limits):
                limits.append({'rule_id': 'native_checkers_not_confirmed',
                               'message': 'Positive native checker inventory is required.'})
        limitations.extend({**entry, 'context_id': context['context_id']} for entry in limits)
        if observed != [context['analysis_file']]:
            limitations.append({'context_id': context['context_id'], 'rule_id': 'native_target_not_confirmed'})
            continue
        for finding in native_findings:
            origin, path, sha = locations[finding['path']]
            value = {**finding, 'path': path, 'origin': origin, 'source_sha256': sha,
                'context_id': context['context_id'], 'native_evidence_sha256': native_evidence_sha256,
                'locations': [{'origin': locations[p['path']][0], 'path': locations[p['path']][1],
                    'source_sha256': locations[p['path']][2], 'line': p['line'], 'column': p['column']}
                    for p in finding['locations']]}
            value['id'] = 'cpp-context-' + _digest(_canonical({k: v for k, v in value.items()
                                                             if k != 'native_evidence_sha256'}))
            findings.append(value)
        if not any(entry['rule_id'] != 'checkersReport' for entry in limits):
            analyzed.append(context['context_id'])
    if duration > evidence['duration_ms'] * LIMITS['parallel'] + 1000:
        raise ValueError('worker_project_static_duration_invalid')
    required = [c['context_id'] for c in request['contexts']]
    headers = {}
    if header_provenance:
        inventory=['/work/source/'+p for p in request['targets']]
        inventory += ['/work/analysis/generated-baseline/'+p for p in request['generated_files']]
        headers={p:{'included_contexts':[],'parsed_contexts':[],'analyzed_contexts':[]} for p in sorted(inventory)
            if p.lower().endswith(('.h','.hh','.hpp','.hxx','.inc','.ipp','.tpp'))}
        for proof in header_contexts:
            for field,members in [('included_contexts','include_observed_files'),('parsed_contexts','parsed_token_files'),('analyzed_contexts','normal_pass_token_files')]:
                for path in proof[members]:
                    if path in headers:
                        state=headers[path]
                        state[field].append(proof['context_id'])
        context_complete=(len(header_contexts)==len(required) and all(
            p['normal_pass_completed'] and p['physical_token_origin_verified'] for p in header_contexts))
        population_complete=context_complete and all(row['analyzed_contexts'] for row in headers.values())
    return {'required_contexts': required, 'attempted_contexts': attempted, 'analyzed_contexts': analyzed,
        'complete': analyzed == required, 'findings': findings, 'limitations': limitations,
        **({'modeled_inputs': modeled_inputs, 'compiler_environment_sha256': environment_model['native_evidence_sha256']}
           if environment_model is not None else {}),
        'native_evidence_sha256': native_evidence_sha256, 'compiler_evidence_sha256': request['compiler_evidence_sha256'],
        'static_analysis_executed': bool(attempted), 'analyzer_header_coverage_verified': False,
        **({'header_context_evidence':header_contexts,'header_context_evidence_complete':context_complete,
            'header_population':headers,'header_population_complete':population_complete,
            'header_unvisited_files':sorted(p for p,row in headers.items() if not row['included_contexts']),
            'header_tool_manifest_sha256':HEADER_TOOL_MANIFEST_SHA256} if header_provenance else {}),
        'model_limits': (['Observed GCC predefines and compiler-resolved dependency bytes bind each context.',
                          'Named public C/C++ and POSIX headers use hash-verified upstream library models, not implementation-header analysis.',
                          'Compiler header visitation does not establish analyzer header coverage.']
                         if environment_model is not None else
                         ['Compiler predefined macro equivalence is not established.',
                          'Header visitation evidence belongs to the separate compiler pass.']),
        'human_review_completed': False, 'production_qualified': False}


def run_project_static():
    import sys
    try:
        raw = sys.stdin.buffer.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            raise ValueError('worker_project_static_request_limit')
        result = collect_project_static(json.loads(raw))
    except Exception as exc:
        code = str(exc)
        if re.fullmatch(r'worker_project_static_[a-z_]+', code) is None:
            code = 'worker_project_static_unavailable'
        print(json.dumps({'schema': 'nico.cpp-project-static-failure.v1', 'error': code}))
        sys.exit(1)
    print(_canonical(result).decode())


PROGRAM = ('import base64, hashlib, json, os, re, shlex, stat, subprocess, time, zlib\n'
    'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n'
    + f'TOOL_VERSION={TOOL_VERSION!r}\nCHECKS={CHECKS!r}\nLIMITS={LIMITS!r}\n'
    + f'STREAM_LIMIT={STREAM_LIMIT}\nREQUEST_LIMIT={REQUEST_LIMIT}\nXML_LIMIT={XML_LIMIT}\nXML_COMPRESSED_LIMIT={XML_COMPRESSED_LIMIT}\n'
    + f'GENERATED_FILE_LIMIT={GENERATED_FILE_LIMIT}\n'
    + f'HEADER_SCHEMA={HEADER_SCHEMA!r}\nHEADER_TOOL_MANIFEST_SHA256={HEADER_TOOL_MANIFEST_SHA256!r}\nHEADER_APPLIER_SHA256={HEADER_APPLIER_SHA256!r}\n'
    + STATIC_ENV_SUPPORT + '\n'
    + '\n'.join(inspect.getsource(f) for f in (_canonical, _digest, _source_path, safe_compile_argv,
        _regular_bytes, _run, _project_option, _stable_bytes, _extra_option, _syntax_argv,
        _verify_input, _encode_xml, _require, validate_header_tool_receipt, _header_standard, _analyzer_macro_arguments,
        _static_plan, collect_project_static, run_project_static))
    + '\nrun_project_static()\n')


def run_project_static_stage(source, targets, image, database, snapshot, compiler_raw, *,
                             retain=lambda result: None, retain_artifact, checkpoint=lambda: None,
                             command=None, extended_compiler_budget=None, compiler_environment=False,
                             header_provenance=False, collect_completed_compiler_failures=False):
    """Analyze verified inputs in a fresh bounded, no-network/noexec sandbox.

    Reuses the existing controller input and isolation boundary. The preceding
    1,800-second build/compiler executor is never extended or left running.
    A stage receipt is evidence, not worker authority or production selection.
    """
    if (type(compiler_environment) is not bool or type(header_provenance) is not bool
            or type(collect_completed_compiler_failures) is not bool
            or header_provenance and not compiler_environment):
        raise ValueError('worker_project_static_stage_environment_flag_invalid')
    from uuid import uuid4
    from nico.assessment_cpp_full_project import MAX_SOURCE_BYTES, _json
    if collect_completed_compiler_failures and not (compiler_environment and header_provenance):
        raise ValueError('worker_project_static_stage_compiler_collection_policy_invalid')
    from nico.assessment_cpp_full_project_execution import (_command, _inputs, ANALYSIS_USER,
        ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM, boundary_valid)
    from nico.assessment_cpp_configuration_probe import SCRATCH_PROGRAM
    from nico.assessment_cpp_project_snapshot import PROJECT_RESTORE_PROGRAM
    from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, resources_for, docker_resource_args
    if (not isinstance(image, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', image) is None
            or not callable(retain_artifact) or not callable(checkpoint)):
        raise ValueError('worker_project_static_stage_contract_invalid')
    profile = BASELINE_QUALIFICATION_PROFILE
    resources = resources_for(profile)
    command = _command if command is None else command
    start = time.monotonic()
    deadline = start + STAGE_EXECUTION_SECONDS
    name = 'nico-project-static-' + uuid4().hex
    created = False
    result = {'schema': 'nico.cpp-project-static-stage.v1', 'status': 'UNPROVEN',
        'phase': 'validate_inputs', 'complete': False, 'image_config_digest': image,
        'source_population_sha256': _digest(_canonical(targets)),
        'request_sha256': None, 'snapshot_population_sha256': None, 'compiler_evidence_sha256': None,
        'execution_budget_seconds': STAGE_EXECUTION_SECONDS, 'wall_budget_seconds': STAGE_WALL_SECONDS,
        'budget_policy': dict(STAGE_BUDGET), 'duration_ms': 0,
        'resource_profile': profile, 'operations': [], 'boundary': None, 'boundary_verified': False,
        'scratch_capacity_verified': False, 'scratch_capacity_bytes': None,
        'memory_peak_bytes': None, 'cleanup_verified': False, 'analysis': None,
        'error': None, 'production_qualified': False}

    def save():
        result['duration_ms'] = int((time.monotonic() - start) * 1000)
        retain(result)

    def guarded_checkpoint():
        checkpoint()
        if time.monotonic() >= deadline:
            raise ValueError('worker_project_static_stage_deadline')

    def observe(key, argv, *, data=None, limit=65536, seconds=15, external=False):
        guarded_checkpoint()
        before = time.monotonic()
        # The command owns the already-clipped timeout. Raising the shared
        # deadline from its checkpoint discards bytes it has read. Keep lease
        # and cancellation checks live, then retain the timeout outcome before
        # the post-return shared-deadline check rejects it.
        observed = command(argv, checkpoint=checkpoint, input_bytes=data,
                           timeout=min(seconds, deadline-before), limit=limit, native_exit=True)
        raw = observed['output']
        operation = {'id': key, 'invocation': argv, 'exit_code': observed['exit_code'],
            'timed_out': observed['timed_out'], 'output_truncated': observed['output_truncated'],
            'duration_ms': int((time.monotonic()-before)*1000),
            'output': None if external else base64.b64encode(raw).decode('ascii'), 'output_sha256': _digest(raw)}
        if external:
            operation['output_artifact'] = None
        result['operations'].append(operation)
        save()
        if external:
            try:
                reference = retain_artifact(key, raw)
            except Exception as exc:
                raise ValueError('worker_project_static_stage_artifact_retention_failed') from exc
            expected = {'path': 'artifacts/' + key + '-' + _digest(raw) + '.json',
                        'sha256': _digest(raw), 'bytes': len(raw)}
            if reference != expected or type(reference.get('bytes')) is not int:
                raise ValueError('worker_project_static_stage_artifact_reference_invalid')
            operation['output_artifact'] = reference
            save()
        # Preserve returned bytes before rejecting a late response or retention.
        guarded_checkpoint()
        return observed

    def require(key, argv, **kwargs):
        response = observe(key, argv, **kwargs)
        if response['exit_code'] != 0 or response['timed_out'] or response['output_truncated']:
            raise ValueError('worker_project_static_stage_operation_failed')
        return response['output']

    save()
    try:
        guarded_checkpoint()
        if collect_completed_compiler_failures:
            from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
            selected = extended_compiler_budget
            if selected is None:
                selected = _json(compiler_raw)['schema'] == 'nico.cpp-project-compiler-evidence.v2'
            initial_compiler_request = project_compiler_request(database, targets, snapshot, extended_budget=selected)
            collection = validate_project_compiler_collection(compiler_raw, initial_compiler_request, snapshot)
            result.update(schema='nico.cpp-project-static-stage.v4', collection_complete=False,
                compiler_collection=collection, static_collection=None,
                snapshot_population_sha256=collection['snapshot_population_sha256'],
                compiler_evidence_sha256=collection['native_evidence_sha256'])
            request = None  # The actual request is bound after native environment capture.
        else:
            request = project_static_request(database, targets, snapshot, compiler_raw,
                extended_compiler_budget=extended_compiler_budget)
            result.update(request_sha256=_digest(_canonical(request)),
                snapshot_population_sha256=request['snapshot_population_sha256'],
                compiler_evidence_sha256=request['compiler_evidence_sha256'])
        files = _inputs({'targets': targets, 'configuration': {'source_byte_limit': MAX_SOURCE_BYTES}},
                        Path(source), guarded_checkpoint)
        result['phase'] = 'sandbox'; save()
        metadata = _json(require('static-image', ['docker', 'image', 'inspect', image]))
        if not isinstance(metadata, list) or len(metadata) != 1 or metadata[0].get('Id') != image:
            raise ValueError('worker_project_static_stage_image_mismatch')
        created = True
        require('static-create', ['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(profile, executable=False), '--log-driver=none',
            '--env=HOME=/work', '--env=TMPDIR=/work', '--entrypoint=sleep', image, str(STAGE_WALL_SECONDS + 5)])
        require('static-start', ['docker', 'start', name])
        private = _json(require('static-private', ['docker', 'exec', '--user='+ANALYSIS_USER, name,
            'python3', '-I', '-S', '-c', ANALYSIS_SETUP_PROGRAM]))
        if private != {'uid': 1001, 'gid': 1001, 'private': True}:
            raise ValueError('worker_project_static_stage_private_invalid')
        boundary = _json(require('static-boundary-before', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        if not boundary_valid(boundary, source_required=False, profile=profile, executable=False):
            raise ValueError('worker_project_static_stage_boundary_invalid')
        payload = _canonical(files)
        transferred = _json(require('static-source', ['docker', 'exec', '--user=0:0', '--interactive', name,
            'python3', '-I', '-S', '-c', INPUT_PROGRAM, str(len(payload))], data=payload,
            limit=4*1024*1024, seconds=30))
        if transferred != targets:
            raise ValueError('worker_project_static_stage_source_mismatch')
        result['boundary'] = _json(require('static-boundary', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        result['boundary_verified'] = boundary_valid(result['boundary'], profile=profile, executable=False)
        if not result['boundary_verified']:
            raise ValueError('worker_project_static_stage_boundary_invalid')
        storage = _json(require('static-storage', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', SCRATCH_PROGRAM]))
        if (not isinstance(storage, dict) or type(storage.get('capacity_bytes')) is not int
                or storage['capacity_bytes'] != resources['tmpfs_bytes']
                or type(storage.get('available_bytes')) is not int
                or not 64*1024*1024 <= storage['available_bytes'] <= storage['capacity_bytes']):
            raise ValueError('worker_project_static_stage_storage_invalid')
        result.update(scratch_capacity_verified=True, scratch_capacity_bytes=storage['capacity_bytes'], phase='restore')
        restore = {'schema': 'nico.cpp-project-restore.v1', 'files': snapshot['files'],
                   'file_population_sha256': snapshot['file_population_sha256']}
        restored = _json(require('static-restore', ['docker', 'exec', '--user='+ANALYSIS_USER,
            '--interactive', name, 'python3', '-I', '-S', '-c', PROJECT_RESTORE_PROGRAM],
            data=_canonical(restore), limit=4*1024*1024, seconds=30))
        expected_files = (initial_compiler_request['generated_files']
                          if collect_completed_compiler_failures else request['generated_files'])
        expected_population = (initial_compiler_request['snapshot_population_sha256']
                               if collect_completed_compiler_failures else request['snapshot_population_sha256'])
        if restored != {'files': expected_files, 'file_population_sha256': expected_population}:
            raise ValueError('worker_project_static_stage_restore_mismatch')
        if compiler_environment:
            from nico.assessment_cpp_static_environment import (environment_request, validate_environment,
                ENV_PROGRAM, ENV_STREAM_LIMIT)
            result['phase'] = 'compiler_environment'; save()
            selected = extended_compiler_budget
            if selected is None:
                selected = _json(compiler_raw)['schema'] == 'nico.cpp-project-compiler-evidence.v2'
            compiler_request = project_compiler_request(database, targets, snapshot, extended_budget=selected)
            env_request = environment_request(compiler_request, compiler_raw, image,
                collect_completed_compiler_failures=collect_completed_compiler_failures, snapshot=snapshot)
            env_observed = observe('project-static-environment', ['docker', 'exec', '--user='+ANALYSIS_USER,
                '--interactive', name, 'python3', '-I', '-S', '-c', ENV_PROGRAM],
                data=_canonical(env_request), limit=ENV_STREAM_LIMIT, seconds=40, external=True)
            if env_observed['exit_code'] != 0 or env_observed['timed_out'] or env_observed['output_truncated']:
                raise ValueError('worker_project_static_stage_environment_failed')
            model = validate_environment(env_observed['output'], env_request)
            result['compiler_environment'] = {'schema': model['schema'],
                'artifact': result['operations'][-1]['output_artifact'],
                'native_evidence_sha256': model['native_evidence_sha256'],
                'compiler_evidence_sha256': model['compiler_evidence_sha256'],
                'image_config_digest': model['image_config_digest'],
                'contexts': len(model['contexts']), 'queries': len(model['queries']),
                'headers': len(model['headers']), 'header_bytes': model['header_bytes'],
                'header_population_sha256': model['header_population_sha256'],
                'models': model['models'], 'model_policy': model['model_policy']}
            request = project_static_request(database, targets, snapshot, compiler_raw,
                extended_compiler_budget=extended_compiler_budget, environment=model,
                header_provenance=header_provenance,
                collect_completed_compiler_failures=collect_completed_compiler_failures)
            result.update(schema=('nico.cpp-project-static-stage.v4' if collect_completed_compiler_failures
                                  else 'nico.cpp-project-static-stage.v3' if header_provenance
                                  else 'nico.cpp-project-static-stage.v2'), request_sha256=_digest(_canonical(request)))
            save(); guarded_checkpoint()
        result['phase'] = 'analysis'; save()
        observed = observe('project-static-evidence', ['docker', 'exec', '--user='+ANALYSIS_USER,
            '--interactive', name, 'python3', '-I', '-S', '-c', PROGRAM],
            data=_canonical(request), limit=STREAM_LIMIT, seconds=550, external=True)
        if observed['exit_code'] != 0 or observed['timed_out'] or observed['output_truncated']:
            raise ValueError('worker_project_static_stage_analysis_failed')
        primary_artifact = result['operations'][-1]['output_artifact']
        primary_analysis = validate_project_static(observed['output'], request)
        primary_raw = observed['output']
        fallback_raw = None
        result['analysis'] = {**primary_analysis, 'artifact': primary_artifact}
        save()
        guarded_checkpoint()  # Parsing and proof retention belong to this phase.
        if compiler_environment and (not result['analysis']['complete'] or (
                collect_completed_compiler_failures
                and not result['analysis'].get('header_context_evidence_complete'))):
            from nico.assessment_cpp_clang_fallback import (PROGRAM as CLANG_FALLBACK_PROGRAM,
                STREAM_LIMIT as CLANG_FALLBACK_STREAM_LIMIT, clang_fallback_request,
                validate_clang_fallback, merge_static_analysis)
            fallback_request = clang_fallback_request(request, primary_analysis,
                extended_budget=True, contention_aware=True, multi_file_diagnostics=True)
            if fallback_request['contexts']:
                result['phase'] = 'analysis_fallback'; save()
                guarded_checkpoint()
                # Allocate only the remaining shared envelope, reserving the
                # existing ten-second return/cleanup margin inside that cap.
                # The request's 480/120/parallel-2 maxima remain unchanged.
                return_margin_ms = (STAGE_WALL_SECONDS - STAGE_EXECUTION_SECONDS) * 1000
                budget_ms = min(fallback_request['limits']['wall_seconds'] * 1000,
                    int((deadline - time.monotonic()) * 1000) - return_margin_ms)
                if budget_ms <= 0:
                    raise ValueError('worker_project_static_stage_deadline')
                fallback_observed = observe('project-static-clang-fallback',
                    ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name,
                     'python3', '-I', '-S', '-c', CLANG_FALLBACK_PROGRAM, str(budget_ms)],
                    data=_canonical(fallback_request), limit=CLANG_FALLBACK_STREAM_LIMIT,
                    seconds=fallback_request['limits']['wall_seconds']+10, external=True)
                if (fallback_observed['exit_code'] != 0 or fallback_observed['timed_out']
                        or fallback_observed['output_truncated']):
                    raise ValueError('worker_project_static_stage_fallback_failed')
                fallback = validate_clang_fallback(fallback_observed['output'], fallback_request, request,
                    wall_budget_ms=budget_ms)
                fallback_raw = fallback_observed['output']
                merged = merge_static_analysis(primary_analysis, fallback)
                result['analysis'] = {**merged, 'artifact': primary_artifact,
                    'fallback_artifact': result['operations'][-1]['output_artifact']}
                result['clang_fallback'] = merged['clang_fallback']
                save(); guarded_checkpoint()
        if collect_completed_compiler_failures:
            from nico.assessment_cpp_static_collection import validate_project_static_collection
            result['static_collection'] = validate_project_static_collection(
                primary_raw, request, collection, fallback_raw=fallback_raw)
            if result['static_collection']['analysis'] != {
                    k:v for k,v in result['analysis'].items()
                    if k not in {'artifact','fallback_artifact'}}:
                raise ValueError('worker_project_static_stage_collection_mismatch')
            if result['static_collection']['failed_contexts']:
                result['error'] = 'worker_project_static_stage_target_failure'
        else:
            if not result['analysis']['complete']:
                raise ValueError('worker_project_static_stage_analysis_incomplete')
            if header_provenance and not result['analysis'].get('header_context_evidence_complete'):
                raise ValueError('worker_project_static_stage_header_evidence_incomplete')
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, ValueError) else ''
        result['error'] = (code if re.fullmatch(r'worker_project_static_stage_[a-z_]+', code)
                           else 'worker_project_static_stage_interrupted' if isinstance(exc, KeyboardInterrupt)
                           else 'worker_project_static_stage_failed')
    finally:
        if created:
            try:
                observed = command(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'],
                    checkpoint=lambda: None, timeout=2, limit=1024, native_exit=True)
                if observed['exit_code'] == 0 and not observed['timed_out'] and not observed['output_truncated']:
                    peak = int(observed['output'].strip())
                    if 0 <= peak <= resources['memory_bytes']:
                        result['memory_peak_bytes'] = peak
            except (Exception, KeyboardInterrupt):
                pass
            try:
                removed = command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                                  timeout=5, limit=4096, native_exit=True)
                result['cleanup_verified'] = (removed['exit_code'] == 0 and not removed['timed_out']
                                              and not removed['output_truncated'])
            except (Exception, KeyboardInterrupt):
                pass
        if created and not result['cleanup_verified']:
            result['error'] = result['error'] or 'worker_project_static_stage_cleanup_failed'
        result['complete'] = bool(not result['error'] and result['analysis'] and result['analysis']['complete']
                                  and result['boundary_verified'] and result['cleanup_verified'])
        if collect_completed_compiler_failures:
            result['collection_complete'] = bool(
                (result.get('static_collection') or {}).get('collection_complete') is True
                and result['error'] in {None,'worker_project_static_stage_target_failure'}
                and result['boundary_verified'] and result['cleanup_verified'])
            if result['collection_complete'] and not result['complete']:
                result['phase'] = 'collection_completed_target_failure'
        if result['complete']:
            result.update(status='STATIC_ANALYSIS_EXECUTED', phase='completed')
        save()
    return result
