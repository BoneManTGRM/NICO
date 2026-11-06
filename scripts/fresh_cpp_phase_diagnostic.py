"""Fresh public-source diagnostic; no archive intake and no qualification credit.

This entry point is deliberately separate from the production CLI. It stops
after fresh primary collection, even when that collection looks successful.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from nico.assessment_cpp_full_project_execution import _command
from nico.assessment_cpp_project_static import (
    PROGRAM, STREAM_LIMIT, _canonical, _digest, _execution, validate_project_static,
)

PHASES = {
    'Tokenizer::createTokens': 'token_creation',
    'Tokenizer::simplifyTokens1::simplifyTokenList1::simplifyTypedef': 'typedef_simplification',
    'Tokenizer::simplifyTokens1::simplifyTokenList1::simplifyTemplates': 'template_simplification',
    'Tokenizer::simplifyTokens1::createAst': 'ast_creation',
    'Tokenizer::simplifyTokens1::createSymbolDatabase': 'symbol_database',
}
MAX_ROWS = 16
CONSOLE_LIMIT = 16384
EXPECTED_CONTEXTS = 577


def phase_measurements(raw):
    """Only completed fixed-name timings; absence is unknown, never zero."""
    result = {name: {'state': 'unavailable'} for name in PHASES.values()}
    if not isinstance(raw, bytes) or len(raw) > 65536:
        return result
    for raw_line in raw.decode('utf-8', errors='replace').splitlines(keepends=True):
        line = raw_line.rstrip('\r\n')
        name, separator, value = line.rpartition(': ')
        if not separator or name not in PHASES:
            continue
        key = PHASES[name]
        if result[key]['state'] != 'unavailable':
            result[key] = {'state': 'invalid'}
            continue
        try:
            if not raw_line.endswith('\n'):
                raise ValueError('incomplete_timing')
            if not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,9})?(?:e[+-]?[0-9]{1,2})?s', value):
                raise ValueError('timing')
            seconds = Decimal(value[:-1])
            if not seconds.is_finite() or not 0 <= seconds <= 540:
                raise ValueError('timing')
            result[key] = {'state': 'available', 'cpu_microseconds': int(seconds * 1000000)}
        except (ValueError, InvalidOperation):
            result[key] = {'state': 'invalid'}
    return result


def diagnostic_program(binding=None):
    suffix = '\nrun_project_static()\n'
    if not PROGRAM.endswith(suffix):
        raise ValueError('diagnostic_program_changed')
    verification = ''
    replacement = ''
    if binding is not None:
        from scripts.build_cpp_phase_boundaries import FILES, BINARY
        hashes = {FILES[k]:v for k,v in binding['files'].items()}
        hashes[BINARY] = binding['diagnostic_binary_sha256']
        verification = ('\nfor _phase_path, _phase_sha in ' + repr(hashes) + '.items():\n'
            "    if _digest(_regular_bytes(_phase_path, 67108864)) != _phase_sha:\n"
            "        raise ValueError('phase_runtime_tool_identity')\n")
        replacement = "\n        actual[0] = " + repr(BINARY)
    # No selection, scheduler, clock, source verification or resource change.
    return PROGRAM[:-len(suffix)] + verification + '''
original_run = _run
def _run(argv, stem, deadline, environment):
    actual = list(argv)
    if actual[0] == '/usr/local/bin/cppcheck':
        if '--version' not in actual:
            actual.append('--showtime=file')''' + replacement + '''
    return original_run(actual, stem, deadline, environment)
run_project_static()
'''


def empty_summary(state):
    return {'schema': 'nico.fresh-cpp-phase-diagnostic.v1', 'state': state,
        'input_origin': 'fresh_public_source_configuration',
        'historical_environment_equivalent': False, 'assessment_completed': False,
        'full_project_qualified': False, 'production_qualified': False,
        'expected_contexts': EXPECTED_CONTEXTS, 'observed_contexts': None,
        'precise_termination_hotspot_known': False,
        'timing_semantics': 'completed_cpu_phases_only_may_overlap_includes_observer_cost',
        'records': []}


def summarize(observed, request, binding=None):
    summary = empty_summary('unavailable')
    try:
        if (not isinstance(request, dict) or len(request['contexts']) != EXPECTED_CONTEXTS
                or request['limits'] != {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 2}):
            raise ValueError('request')
        if (not isinstance(observed, dict) or observed.get('exit_code') != 0
                or observed.get('timed_out') is not False
                or observed.get('output_truncated') is not False):
            return summary
        raw = observed['output']
        if not isinstance(raw, bytes) or not 0 < len(raw) <= STREAM_LIMIT:
            raise ValueError('output')
        proof = validate_project_static(raw, request)
        records = json.loads(raw)['records']
        summary.update(state='collected', request_sha256=_digest(_canonical(request)),
            native_evidence_sha256=_digest(raw), observed_contexts=len(proof['attempted_contexts']),
            source_population_sha256=_digest(_canonical(request['targets'])),
            collection_duration_ms=json.loads(raw)['duration_ms'])
        executed = [(i, row) for i, row in enumerate(records) if row['execution'] is not None]
        if binding is not None:
            from scripts.build_cpp_phase_boundaries import canonical, BINARY
            summary['boundary_binding_sha256'] = _digest(canonical(binding))
            summary['diagnostic_image_sha256'] = binding['image'][7:]
            summary['diagnostic_binary_sha256'] = binding['diagnostic_binary_sha256']
            summary['planned_probe_invocations_sha256'] = _digest(_canonical([
                [BINARY, *context['analyzer_invocation'][1:], '--showtime=file']
                for context in request['contexts']]))
        summary['omitted_executed_records'] = max(0, len(executed) - MAX_ROWS)
        for index, row in executed[:MAX_ROWS]:
            execution = row['execution']
            _, output = _execution(execution, 93000)
            summary['records'].append({'context_index': index,
                'exit_code': execution['exit_code'], 'timed_out': execution['timed_out'],
                'output_truncated': execution['output_truncated'],
                'duration_ms': execution['duration_ms'],
                'phases': phase_measurements(output)})
            if binding is not None:
                from scripts.cpp_phase_boundaries import parse_markers
                summary['records'][-1]['boundaries'] = (parse_markers(output) if not execution['output_truncated']
                    else {'state':'unavailable','last_boundary':None,'precise_hotspot_known':False})
        return summary
    except Exception:
        return empty_summary('invalid')


class DiagnosticFinished(BaseException):
    """Unwind every sandbox finally block before any acceptance/fallback/runtime."""


def diagnostic_command(run, emit, binding=None):
    used = False

    def command(argv, **kwargs):
        nonlocal used
        if not isinstance(argv, list) or not argv or argv[-1] != PROGRAM:
            return run(argv, **kwargs)
        try:
            if (used or len(argv) != 10
                    or argv[:4] != ['docker', 'exec', '--user=1001:1001', '--interactive']
                    or argv[-5:-1] != ['python3', '-I', '-S', '-c']):
                raise ValueError('diagnostic_command_invalid')
            request = json.loads(kwargs['input_bytes'])
            if (request.get('schema') != 'nico.cpp-project-static-request.v4'
                    or request.get('compiler_environment', {}).get('physical_header_inputs') is not True
                    or len(request['contexts']) != EXPECTED_CONTEXTS
                    or request['limits'] != {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 2}):
                raise ValueError('diagnostic_request_invalid')
            used = True
            result = run([*argv[:-1], diagnostic_program(binding)], **kwargs)
            summary = summarize(result, request, binding)
        except (Exception, KeyboardInterrupt):
            summary = empty_summary('preparation_or_execution_failed')
        try:
            emit(summary)
        finally:
            # Raw diagnostic execution never reaches the production validator,
            # including on collector/output failure. Sandbox finally blocks run.
            raise DiagnosticFinished()

    return command


def emit_summary(summary):
    # Defend the console boundary even if a future caller passes the wrong object.
    def allowed(value):
        base = empty_summary('unavailable')
        boundary_keys = {'boundary_binding_sha256','diagnostic_image_sha256',
                         'diagnostic_binary_sha256','planned_probe_invocations_sha256'}
        has_boundaries = type(value) is dict and bool(set(value) & boundary_keys)
        if type(value) is not dict or set(value) - (set(base) | boundary_keys | {
                'request_sha256', 'native_evidence_sha256', 'source_population_sha256',
                'collection_duration_ms', 'omitted_executed_records'}):
            return False
        if any(type(value.get(k)) is not type(v) or value.get(k) != v for k, v in base.items()
               if k not in {'state', 'observed_contexts', 'records'}):
            return False
        if value.get('state') not in {'collected', 'unavailable', 'invalid', 'output_limit',
                                     'preparation_or_execution_failed', 'primary_not_executed'}:
            return False
        extra = {'request_sha256', 'native_evidence_sha256', 'source_population_sha256',
                 'collection_duration_ms', 'omitted_executed_records'}
        if has_boundaries:
            extra |= boundary_keys
        if value['state'] == 'collected':
            if set(value) != set(base) | extra or type(value.get('observed_contexts')) is not int:
                return False
        elif set(value) != set(base) or value.get('observed_contexts') is not None or value.get('records') != []:
            return False
        for key in {'request_sha256', 'native_evidence_sha256', 'source_population_sha256'} | boundary_keys:
            if key in value and (type(value[key]) is not str or not re.fullmatch('[a-f0-9]{64}', value[key])):
                return False
        for key, maximum in (('observed_contexts', EXPECTED_CONTEXTS),
                             ('omitted_executed_records', EXPECTED_CONTEXTS), ('collection_duration_ms', 543000)):
            if value.get(key) is not None and (type(value[key]) is not int or not 0 <= value[key] <= maximum):
                return False
        rows = value.get('records')
        if type(rows) is not list or len(rows) > MAX_ROWS:
            return False
        for row in rows:
            if type(row) is not dict or set(row) != {'context_index', 'exit_code', 'timed_out',
                                                    'output_truncated', 'duration_ms', 'phases'} | ({'boundaries'} if has_boundaries else set()):
                return False
            for key, low, high in (('context_index', 0, EXPECTED_CONTEXTS-1), ('exit_code', -255, 255), ('duration_ms', 0, 93000)):
                if type(row[key]) is not int or not low <= row[key] <= high:
                    return False
            if any(type(row[k]) is not bool for k in ('timed_out', 'output_truncated')):
                return False
            if has_boundaries:
                boundary = row['boundaries']
                if type(boundary) is not dict or set(boundary) != {'state','last_boundary','precise_hotspot_known'}:
                    return False
                if boundary['precise_hotspot_known'] is not False:
                    return False
                if boundary['state'] == 'observed':
                    if boundary['last_boundary'] not in {'using_begin','using_end','template_begin','template_end'}: return False
                elif boundary['state'] not in {'unavailable','invalid','capped'} or boundary['last_boundary'] is not None:
                    return False
            phases = row['phases']
            if type(phases) is not dict or set(phases) != set(PHASES.values()):
                return False
            for phase in phases.values():
                if type(phase) is not dict:
                    return False
                if phase.get('state') == 'available':
                    if (set(phase) != {'state', 'cpu_microseconds'} or type(phase['cpu_microseconds']) is not int
                            or not 0 <= phase['cpu_microseconds'] <= 540000000):
                        return False
                elif set(phase) != {'state'} or phase['state'] not in {'invalid', 'unavailable'}:
                    return False
        return True
    try:
        valid = allowed(summary)
    except Exception:
        valid = False
    if not valid:
        summary = empty_summary('invalid')
    encoded = json.dumps(summary, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode()) > CONSOLE_LIMIT:
        encoded = json.dumps(empty_summary('output_limit'))
    print(encoded, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--boundary-binding', type=Path)
    parser.add_argument('--qualification-source', type=Path, required=True)
    parser.add_argument('--unit-test-data', type=Path, required=True)
    parser.add_argument('--producer-source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1] / 'tests/fixtures/cpp'
    args.qualification_manifest = root / 'bitcoin-configuration-benchmark.json'
    args.baseline_execution_contract = root / 'bitcoin-baseline-execution.json'
    args.runtime_scope_contract = root / 'bitcoin-runtime-scope.json'
    for name in ('capture_generated_context', 'project_compiler_evidence', 'project_static_analysis',
                 'extended_compiler_budget', 'compiler_environment', 'capture_enabled_targets',
                 'capture_native_commands', 'materialize_generated_inputs',
                 'collect_completed_compiler_failures', 'accept_completed_collection'):
        setattr(args, name, True)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('diagnostic_fresh_output_required')
        binding = None
        if args.boundary_binding is not None:
            from scripts.build_cpp_phase_boundaries import validate_binding
            with args.boundary_binding.open('rb') as stream:
                raw = stream.read(16385)
            if len(raw)>16384: raise ValueError('phase_binding_limit')
            binding = validate_binding(json.loads(raw),args.image)
        from scripts.qualify_cpp_project_configuration import qualify_configuration_checkout
        qualify_configuration_checkout(args, command=diagnostic_command(_command, emit_summary, binding),
                                       diagnostic_primary_only=True)
    except DiagnosticFinished:
        return 1  # Never a qualification success exit.
    except (Exception, KeyboardInterrupt):
        emit_summary(empty_summary('preparation_or_execution_failed'))
        return 1
    emit_summary(empty_summary('primary_not_executed'))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
