"""Complete collection of supported compiler outcomes, never target success.

The original compiler validator and its coverage decisions remain authoritative.
This additive v1 consumer recognizes only an actual generated-source #error
directive failure whose diagnostic is bound to immutable captured bytes.
"""
from __future__ import annotations

import base64
import re

from nico.assessment_cpp_configuration import decode_stream
from nico.assessment_cpp_full_project import _json, compilation_contexts
from nico.assessment_cpp_project_compiler import (
    REQUEST_LIMIT, _canonical, _compiler_limits, _digest, _syntax_argv,
    validate_project_compiler,
)
from nico.assessment_cpp_project_snapshot import validate_project_snapshot


def _bound_snapshot(request, snapshot):
    """Recheck the supplied validated plan without changing its native identity."""
    fields = {'schema', 'database_sha256', 'context_membership_sha256',
              'snapshot_population_sha256', 'targets', 'generated_files',
              'generated_header_candidates', 'contexts', 'limits'}
    if (not isinstance(request, dict) or set(request) != fields
            or len(_canonical(request)) > REQUEST_LIMIT
            or not isinstance(request['contexts'], list)
            or not 1 <= len(request['contexts']) <= 20000
            or any(not isinstance(c, dict) or type(c.get('index')) is not int
                   for c in request['contexts'])
            or not isinstance(request['generated_files'], dict)
            or any(not isinstance(item, dict) or set(item) != {'sha256', 'bytes'}
                   or type(item['bytes']) is not int
                   for item in request['generated_files'].values())):
        raise ValueError('worker_project_compiler_collection_request_invalid')
    _compiler_limits(request)
    rows = []
    for context in request['contexts']:
        row = {key: context[key] for key in ('directory', 'file', 'arguments')}
        if context['output'] is not None:
            row['output'] = context['output']
        rows.append(row)
    contexts = compilation_contexts(_canonical(rows), request['targets'], '/work/build')
    # Upstream bound the actual database bytes. Re-serialization above verifies
    # context identities, not the original database's literal byte digest.
    if (not isinstance(request['database_sha256'], str)
            or re.fullmatch(r'[0-9a-f]{64}', request['database_sha256']) is None
            or request['context_membership_sha256'] != contexts['context_membership_sha256']):
        raise ValueError('worker_project_compiler_collection_request_invalid')
    contexts['database_sha256'] = request['database_sha256']
    validate_project_snapshot(snapshot, contexts)
    files = {path: {'sha256': item['sha256'], 'bytes': item['bytes']}
             for path, item in snapshot['files'].items()}
    if (request['generated_files'] != files
            or request['snapshot_population_sha256'] != snapshot['file_population_sha256']
            or request['generated_header_candidates'] != snapshot['header_candidates']):
        raise ValueError('worker_project_compiler_collection_snapshot_mismatch')
    for supplied, context in zip(request['contexts'], contexts['contexts']):
        invocation, analysis_file = _syntax_argv(context, files)
        if supplied != {**context, 'invocation': invocation, 'analysis_file': analysis_file}:
            raise ValueError('worker_project_compiler_collection_context_mismatch')


def _generated_directive(context, record, snapshot):
    execution = record['execution']
    if (context['origin'] != 'generated' or execution is None
            or execution['exit_code'] != 1 or execution['timed_out']
            or execution['output_truncated'] or record['error'] is not None
            or record['dependency_bytes'] != '' or record['dependency_sha256'] is not None
            or record['source_dependencies'] != {} or record['generated_dependencies'] != {}
            or record['toolchain_dependencies'] != []):
        raise ValueError('worker_project_compiler_collection_failure_unsupported')
    output = decode_stream(execution['output'])
    text = output.decode('utf-8')
    if '\0' in text or '\r' in text:
        raise ValueError('worker_project_compiler_collection_diagnostic_invalid')
    pattern = re.compile(re.escape(context['analysis_file'])
                         + r':([1-9][0-9]*):([1-9][0-9]*): error: #error(?:[ \t]+(.*))?')
    diagnostics = []
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match is not None:
            diagnostics.append(match)
        elif line and not (re.fullmatch(r'[ \t]*[1-9][0-9]*[ \t]*\|.*', line)
                           or re.fullmatch(r'[ \t]*\|[ \t]*[\^~]+[ \t]*', line)):
            # Other errors, warnings, notes, permission failures and unknown
            # collector output are outside this deliberately narrow v1.
            raise ValueError('worker_project_compiler_collection_diagnostic_invalid')
    if len(diagnostics) != 1:
        raise ValueError('worker_project_compiler_collection_diagnostic_invalid')
    match = diagnostics[0]
    line_number, column = int(match[1]), int(match[2])
    item = snapshot['files'][context['path']]
    source = base64.b64decode(item['base64'], validate=True)
    lines = source.split(b'\n')
    if line_number > len(lines):
        raise ValueError('worker_project_compiler_collection_directive_mismatch')
    directive = lines[line_number - 1].removesuffix(b'\r').decode('utf-8')
    found = re.fullmatch(r'([ \t]*#[ \t]*)error(?:[ \t]+(.*))?', directive)
    if (found is None or any(token in directive for token in ('\\', '/*', '*/', '//'))
            or column != len(found[1].expandtabs(8)) + 1
            or (match[3] or '').strip(' \t') != (found[2] or '').strip(' \t')):
        raise ValueError('worker_project_compiler_collection_directive_mismatch')
    return {'context_id': context['context_id'], 'path': context['path'],
            'analysis_file': context['analysis_file'], 'source_sha256': item['sha256'],
            'source_bytes': item['bytes'], 'line': line_number, 'column': column,
            'directive': directive, 'output_sha256': execution['output_sha256'],
            'output_bytes': len(output), 'classification': 'generated_source_error_directive'}


def validate_project_compiler_collection(raw, request, snapshot):
    """Validate complete collection while preserving actual compiler failures.

    Request and snapshot come from the existing validated immutable intake.
    Their semantic/byte bindings are checked again here. Unknown failures raise;
    they never turn an unavailable or partial run into complete collection.
    """
    try:
        _bound_snapshot(request, snapshot)
        compiler = validate_project_compiler(raw, request)
        evidence = _json(raw)
        required = compiler['required_contexts']
        if compiler['attempted_contexts'] != required:
            raise ValueError('worker_project_compiler_collection_unattempted')
        checked = set(compiler['checked_contexts'])
        failures = []
        for context, record in zip(request['contexts'], evidence['records']):
            output = decode_stream(record['execution']['output']).decode('utf-8')
            if context['context_id'] in checked:
                # A zero status cannot hide a retained compiler error.
                if re.search(r'^[^\n]*: (?:fatal )?error:', output, flags=re.MULTILINE):
                    raise ValueError('worker_project_compiler_collection_success_diagnostic')
            else:
                failures.append(_generated_directive(context, record, snapshot))
        failed = [row['context_id'] for row in failures]
        if [row for row in required if row not in checked] != failed:
            raise ValueError('worker_project_compiler_collection_population_mismatch')
        return {'schema': 'nico.cpp-project-compiler-collection.v1',
                'collection_complete': True, 'compiler': compiler,
                'failed_contexts': failed, 'unparsed_contexts': list(failed),
                'failures': failures, 'native_evidence_sha256': _digest(raw),
                'request_sha256': _digest(_canonical(request)),
                'snapshot_population_sha256': snapshot['file_population_sha256'],
                'snapshot_canonical_sha256': _digest(_canonical(snapshot))}
    except (KeyError, TypeError, IndexError, UnicodeDecodeError) as error:
        raise ValueError('worker_project_compiler_collection_input_invalid') from error


def collection_summary(proof):
    """Bounded receipt projection; consumers rebuild the proof from raw bytes.

    This function is not a verifier. Its hash never replaces reconstruction.
    The shared shape keeps attempted, completed and unparsed populations apart.
    """
    schema = proof['schema']
    if schema == 'nico.cpp-project-compiler-collection.v1':
        original = proof['compiler']
        required = original['required_contexts']
        attempted = original['attempted_contexts']
        completed = original['checked_contexts']
    elif schema == 'nico.cpp-project-static-collection.v1':
        required = proof['required_contexts']
        attempted = proof['attempted_contexts']
        completed = proof['analyzed_contexts']
    else:
        raise ValueError('worker_project_collection_summary_invalid')
    result = {'schema': schema, 'collection_complete': proof['collection_complete'],
              'proof_sha256': _digest(_canonical(proof)),
              'native_evidence_sha256': proof['native_evidence_sha256'],
              'secondary_native_evidence_sha256': proof.get('fallback_evidence_sha256')}
    for name, values in [('required_contexts', required), ('attempted_contexts', attempted),
                         ('completed_contexts', completed),
                         ('failed_contexts', proof['failed_contexts']),
                         ('unparsed_contexts', proof['unparsed_contexts'])]:
        result[name + '_count'] = len(values)
        result[name + '_sha256'] = _digest(_canonical(values))
    return result
