"""Actual owned-project consumer/receipt/report proof, not production acceptance.

Reuses the existing PostgreSQL/TLS worker protocol control. Its issuer is
synthetic; no production dispatch, actual provider OIDC, or Bitcoin is implied.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from nico.assessment_cpp_full_project import PROFILE, configuration
from nico.assessment_worker_receipts import canonical_bytes
from nico.repository_snapshot import _git_environment
from scripts.qualify_cpp_full_project_control import FIXTURE
from scripts.qualify_cppcheck_worker_control import consume_control


def fixture(*, generated_headers=False, bounded_fuzz=False, project_dependencies=False, project_compiler_options=False):
    """Retain the original fixture by default; opt in to a real configured header."""
    if type(project_dependencies) is not bool or (project_dependencies and not generated_headers):
        raise ValueError('owned_dependency_generated_context_required')
    if type(project_compiler_options) is not bool or (project_compiler_options and not project_dependencies):
        raise ValueError('owned_project_compiler_context_required')
    result = dict(FIXTURE)
    if generated_headers:
        result['config.h.in'] = '#pragma once\n#define NICO_CONFIGURED_OFFSET @NICO_CONFIGURED_OFFSET@\n'
        result['CMakeLists.txt'] += (
            '\nset(NICO_CONFIGURED_OFFSET 0)\n'
            'configure_file(config.h.in generated/config.h @ONLY)\n'
            'target_include_directories(control_sum PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")\n')
        result['sum.cpp'] = ('#include "sum.hpp"\n#include "generated/config.h"\n'
            'int control_sum(int a, int b) { return a + b + NICO_CONFIGURED_OFFSET; }\n')
    if project_dependencies:
        # Exercise actual nested compilation, pinned image headers, linking and
        # library execution. Missing packages cannot become a no-op success.
        result['CMakeLists.txt'] = result['CMakeLists.txt'].replace(
            'add_library(control_sum STATIC sum.cpp)', 'add_subdirectory(src/library)')
        result['src/library/CMakeLists.txt'] = (
            'find_package(Boost 1.74.0 EXACT CONFIG REQUIRED)\n'
            'find_package(SQLite3 3.40 REQUIRED)\n'
            'find_library(NICO_EVENT_LIBRARY NAMES event REQUIRED)\n'
            'find_library(NICO_EVENT_THREADS_LIBRARY NAMES event_pthreads REQUIRED)\n'
            'add_library(control_sum STATIC sum.cpp)\n'
            'target_include_directories(control_sum PUBLIC "${PROJECT_SOURCE_DIR}")\n'
            'target_link_libraries(control_sum PUBLIC Boost::headers SQLite::SQLite3)\n'
            'target_link_libraries(control_sum PUBLIC "${NICO_EVENT_THREADS_LIBRARY}" "${NICO_EVENT_LIBRARY}")\n')
        del result['sum.cpp']
        result['src/library/sum.cpp'] = (
            '#include "sum.hpp"\n#include "generated/config.h"\n'
            '#include <boost/array.hpp>\n#include <boost/version.hpp>\n#include <sqlite3.h>\n'
            '#include <event2/event.h>\n#include <event2/thread.h>\n'
            'static_assert(BOOST_VERSION == 107400, "Pinned Boost headers required");\n'
            'static_assert(SQLITE_VERSION_NUMBER == 3040001, "Pinned SQLite headers required");\n'
            'int control_sum(int a, int b) {\n'
            '    if (sqlite3_libversion_number() != 3040001) return -100;\n'
            '    if (event_get_version_number() != LIBEVENT_VERSION_NUMBER) return -101;\n'
            '    if (evthread_use_pthreads() != 0) return -102;\n'
            '    event_base* base = event_base_new();\n'
            '    if (!base) return -103;\n'
            '    event_base_free(base);\n'
            '    boost::array<int, 2> values = {{a, b}};\n'
            '    return values[0] + values[1] + NICO_CONFIGURED_OFFSET;\n}\n')
    if project_compiler_options:
        result['src/library/CMakeLists.txt'] += (
            'target_compile_options(control_sum PRIVATE -fstack-protector-strong '
            '-fstack-clash-protection -fvisibility=hidden -Werror=return-type)\n')
        result['src/library/CMakeLists.txt'] = result['src/library/CMakeLists.txt'].replace(
            'add_library(control_sum STATIC sum.cpp)', 'add_library(control_sum STATIC sum.cpp helper.c)')
        result['src/library/CMakeLists.txt'] += 'target_compile_features(control_sum PRIVATE c_std_11 cxx_std_20)\n'
        result['sum.hpp'] += '\n#ifdef __cplusplus\nextern "C"\n#endif\nint control_identity(int value);\n'
        result['src/library/helper.c'] = (
            '#include "sum.hpp"\nint control_identity(int value) {\n'
            '    volatile int saved[4] = {value, 0, 0, 0};\n    return saved[0];\n}\n')
        result['src/library/sum.cpp'] = result['src/library/sum.cpp'].replace(
            'return values[0] + values[1] + NICO_CONFIGURED_OFFSET;',
            'return control_identity(values[0] + values[1] + NICO_CONFIGURED_OFFSET);')

    if bounded_fuzz:
        result['corpus/seed'] = 'X'
        result['fuzz.cpp'] = """#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
#ifdef NICO_FUZZ_FAILURE
    if (size == 0) abort();
#endif
    volatile uint64_t sum = 0;
    for (size_t i = 0; i < size; ++i) sum = sum * 33 + data[i];
    return 0;
}
"""
        result['CMakeLists.txt'] = ("cmake_minimum_required(VERSION 3.22)\n"
            "if(NICO_FUZZ_ONLY)\nproject(OwnedFuzz C CXX)\nadd_executable(fuzz_control fuzz.cpp)\n"
            "if(NICO_FUZZ_FAILURE)\ntarget_compile_definitions(fuzz_control PRIVATE NICO_FUZZ_FAILURE=1)\nendif()\n"
            "return()\nendif()\n" + result['CMakeLists.txt'])
    return result


def plan(image, *, negative=False, generated_headers=False, bounded_fuzz=False, project_dependencies=False, project_compiler_options=False):
    fuzz = None
    if bounded_fuzz:
        from nico.assessment_cpp_fuzz import fuzz_plan
        fuzz = fuzz_plan(build_targets=['fuzz_control'],
            cmake_options={'NICO_FUZZ_ONLY': 'ON', 'NICO_FUZZ_FAILURE': 'ON' if negative else 'OFF'},
            targets=[{'name': 'control', 'binary': 'fuzz_control', 'corpus': ['corpus/seed'], 'environment': {}}],
            runs=128, seconds=2, seed=7)
    return {'profile': PROFILE, 'tool_version': '2.17.1', 'image_digest': image,
        'configuration': configuration(units=['main.cpp', 'src/library/sum.cpp' if project_dependencies else 'sum.cpp',
            *(['src/library/helper.c'] if project_compiler_options else [])],
            unit_tests=['negative' if negative else 'unit'], integration_tests=['integration'], compiler_evidence=True, native_test_evidence=True,
            generated_headers=['generated/config.h'] if generated_headers else None, bounded_fuzz=fuzz, nested_cmake=project_dependencies, project_compiler_options=project_compiler_options),
        'targets': {path: hashlib.sha256(text.encode()).hexdigest()
                    for path, text in fixture(generated_headers=generated_headers, bounded_fuzz=bounded_fuzz,
                                              project_dependencies=project_dependencies,
                                              project_compiler_options=project_compiler_options).items()},
        'limits': {'max_attempts': 1, 'wall_seconds': 180, 'lease_seconds': 30},
        'max_receipt_bytes': (8 if bounded_fuzz else 2) * 1024 * 1024}


def render_result(result, output, language):
    """Use the normal client exporter with a clearly labeled owned proof context."""
    from pypdf import PdfReader
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from tests.test_v2_premium_report_renderer import _package
    package = _package(language)
    canonical = package['json']
    record = result.get('persisted_record', result['canonical_record'])
    canonical['identity'].update(repository=record['repository'], commit_sha=record['commit_sha'],
        run_id=record['run_id'], customer_id=record['customer_id'], project_id=record['project_id'])
    canonical['canonical_findings'] = []
    canonical['roadmap'] = []
    canonical['assessment'].update(sections=[], maturity_signal={}, technical_score=None,
        canonical_evidence_adjusted_score=None,
        unavailable_data_notes=[('Prueba de integración con código propio; no es una evaluación de producción.'
            if language == 'es-MX' else 'Owned integration proof only; not a production assessment.')])
    compact = compact_scanner_records({'scan_id': record['scan_id'], 'scanner_results': [record]}, commit_sha=record['commit_sha'])
    canonical['scanner_execution_records'] = compact
    rendered = rebuild_client_artifacts(package)
    stem = 'owned-project-' + language
    pdf = base64.b64decode(rendered['pdf_base64'])
    text = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf)).pages)
    phrase = 'C/C++ project execution' if language == 'en' else 'Ejecución del proyecto C/C++'
    # All formats must expose the same project result, not just the nested JSON.
    assert phrase in rendered['markdown'], 'project_summary_missing_in_markdown'
    assert phrase in rendered['html'], 'project_summary_missing_in_html'
    assert phrase in text, 'project_summary_missing_in_pdf'
    assert rendered['report_finality'] == 'automated_draft'
    assert rendered['human_review_required'] is True
    for key, raw in [('pdf', pdf), ('md', rendered['markdown'].encode()), ('html', rendered['html'].encode()),
                     ('json', canonical_bytes(rendered['json']))]:
        (output / (stem + '.' + key)).write_bytes(raw)
    return {'language': language, 'summary_in_all_formats': True,
        'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'pdf_page_count': len(PdfReader(io.BytesIO(pdf)).pages),
        'automated_draft': True, 'production_report': False}


def write_fixture_tree(git, files):
    """Write owned nested fixtures as Git trees, without checkout or an index.

    mktree takes immediate child names, not slash-separated paths. Build child
    trees first so source/corpus names and exact blob bytes stay unchanged.
    Validate the entire population before writing any objects.
    """
    if not isinstance(files, dict) or not files:
        raise ValueError('owned_fixture_population_invalid')
    root = {}
    for path, text in files.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or any(ord(char) < 32 or char == '\\' for char in path)
                or any(part in {'', '.', '..', '.git'} for part in path.split('/'))
                or not isinstance(text, str)):
            raise ValueError('owned_fixture_path_or_content_invalid')
        parts = path.split('/')
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError('owned_fixture_path_collision')
        if parts[-1] in node:
            raise ValueError('owned_fixture_path_collision')
        node[parts[-1]] = text

    def write(node):
        entries = []
        for name, value in sorted(node.items()):
            if isinstance(value, dict):
                mode, kind, oid = '040000', 'tree', write(value)
            else:
                mode, kind = '100644', 'blob'
                oid = git('hash-object', '-w', '--stdin', data=value.encode())
            entries.append((mode + ' ' + kind + ' ' + oid + '\t' + name).encode() + b'\0')
        return git('mktree', '-z', data=b''.join(entries))

    return write(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--bounded-fuzz', action='store_true')
    parser.add_argument('--project-compiler-options', action='store_true',
                        help='Require source-bound GCC hardening and diagnostic options in the owned control.')
    parser.add_argument('--project-dependencies', action='store_true',
                        help='Exercise pinned Boost/SQLite in the owned nested CMake control.')
    parser.add_argument('--generated-headers', action='store_true', help='Qualify the opt-in frozen generated-header configuration.')
    parser.add_argument('--output', type=Path, default=Path('cpp-full-project-integration'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    release = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    evidence = {'schema': 'nico.cpp-project-integration-control.v1', 'source_sha': release,
        'status': 'UNPROVEN', 'synthetic_issuer': True, 'production_dispatch_exercised': False,
        'production_qualified': False, 'bitcoin_executed': False, 'controls': [], 'reports': []}
    start = time.monotonic()

    def retain():
        # A runner can be killed before finally executes. Persist UNPROVEN
        # before work starts, then preserve each returned native receipt before
        # assertions or report rendering. Atomic replacement prevents torn JSON.
        evidence['duration_ms'] = int((time.monotonic() - start) * 1000)
        temporary = args.output / 'receipt.json.tmp'
        with temporary.open('wb') as handle:
            handle.write(canonical_bytes(evidence))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, args.output / 'receipt.json')

    evidence['stage'] = 'fixture_preparation'
    retain()
    try:
        with tempfile.TemporaryDirectory(prefix='nico-project-owned-') as temporary:
            root = Path(temporary); git_dir = root / 'objects'; git_dir.mkdir()
            env = _git_environment(root)
            env.update(GIT_AUTHOR_NAME='NICO owned fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                GIT_COMMITTER_NAME='NICO owned fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
                GIT_AUTHOR_DATE='2026-09-22T00:00:00+00:00', GIT_COMMITTER_DATE='2026-09-22T00:00:00+00:00')
            def git(*argv, data=None):
                return subprocess.run(['git', *argv], cwd=git_dir, env=env, input=data,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10).stdout.strip().decode()
            git('init', '--bare', '.')
            tree = write_fixture_tree(git, fixture(
                generated_headers=args.generated_headers, bounded_fuzz=args.bounded_fuzz,
                project_dependencies=args.project_dependencies, project_compiler_options=args.project_compiler_options))
            revision = git('commit-tree', tree, data=b'Owned CMake integration fixture\n')
            for negative in (False, True):
                contract = plan(args.image, negative=negative, generated_headers=args.generated_headers, bounded_fuzz=args.bounded_fuzz,
                    project_dependencies=args.project_dependencies, project_compiler_options=args.project_compiler_options); observations = {}
                evidence.update(stage='control_requested', active_control_negative=negative)
                retain()
                result = consume_control(contract, git_dir, tree, revision, release, observations)
                retained = {**observations, **result, 'contract': contract, 'negative': negative}
                evidence['controls'].append(retained)
                evidence['stage'] = 'native_receipt_returned'
                retain()
                from nico.scanner_worker import get_scan
                persisted = get_scan(result['canonical_record']['scan_id'])
                result['persisted_record'] = next(r for r in persisted['scanner_results'] if r.get('tool') == 'cppcheck')
                retained['persisted_record'] = result['persisted_record']
                evidence['stage'] = 'native_receipt_persisted'
                retain()
                record = result['canonical_record']; build = record['cpp_build_evidence']
                assert record['completed'] is True, 'configuration_aware_static_analysis_incomplete'
                assert build['build_completed'] is True, 'project_build_incomplete'
                assert build['source_read_only_verified'] is True
                for group in ('address', 'undefined'):
                    proof = build['native_test_binary_evidence'][group]
                    assert proof['binary_instrumentation_verified'] is True, 'native_test_binary_binding_incomplete'
                    assert proof['tests_passed'] is (not negative), 'native_test_binary_outcome_changed'
                required_units = contract['configuration']['translation_units']
                library_unit = 'src/library/sum.cpp' if args.project_dependencies else 'sum.cpp'
                assert build['compiled_translation_units'] == required_units, 'direct_compiler_population_incomplete'
                assert record['cppcheck_source_coverage']['header_context_verified'] is True, 'compiler_header_context_incomplete'
                for group in ('baseline', 'address', 'undefined'):
                    proof = build['compiler_evidence'][group]
                    assert proof['complete'] is True, 'compiler_configuration_incomplete'
                    assert proof['header_inclusions']['sum.hpp'] == required_units
                    if args.generated_headers:
                        assert proof['generated_header_inclusions'] == {'generated/config.h': [library_unit]}, 'generated_header_inclusion_missing'
                        assert sorted(proof['captured_generated_header_hashes']) == ['generated/config.h']
                        assert proof['toolchain_image_digest'] == contract['image_digest']
                    if args.project_dependencies:
                        assert {'/usr/include/boost/array.hpp', '/usr/include/sqlite3.h',
                                '/usr/include/event2/event.h', '/usr/include/event2/thread.h'}.issubset(
                            proof['toolchain_header_paths']), 'project_dependency_header_evidence_missing'
                    if args.project_compiler_options:
                        native_step = next(r for r in result['receipt']['native']['steps']
                                           if r['id'] == group + '-compiler-evidence')
                        native_proof = json.loads(base64.b64decode(native_step['output'], validate=True))
                        records = {r['unit']: r for r in native_proof['records']}
                        options = ['-fstack-protector-strong', '-fstack-clash-protection',
                                   '-fvisibility=hidden', '-Werror=return-type']
                        for unit in ('src/library/helper.c', library_unit):
                            assert [a for a in records[unit]['invocation'] if a in options] == options, 'project_compiler_options_not_preserved'
                        symbols = base64.b64decode(records['src/library/helper.c']['nm']['output'], validate=True)
                        assert any(line.split()[-1:] == [b'__stack_chk_fail'] for line in symbols.splitlines()), 'owned_stack_protector_symbol_missing'
                    if group != 'baseline':
                        assert proof['object_instrumentation_observed_units'], 'instrumented_object_symbols_missing'
                    assert proof['test_binary_instrumentation_verified'] is False
                assert build['analysis_artifact_isolation_verified'] is True
                assert build['implemented_command_scope_complete'] is (not negative), 'test_truth_changed'
                assert build['requested_scope_complete'] is False
                assert build['full_project_qualified'] is False
                if args.bounded_fuzz:
                    proof = build['bounded_fuzz_evidence']
                    assert build['fuzz_executed'] is True, 'fuzz_execution_not_bound'
                    assert proof['complete'] is (not negative), 'fuzz_outcome_changed'
                    campaign = proof['targets'][0]['phases'][-1]
                    if negative:
                        assert campaign['phase'] == 'campaign' and campaign['status'] == 'failed' and campaign['exit_code'] != 0
                        assert campaign['retained_failure_input']['present'] is True, 'fuzz_failure_input_missing'
                    else:
                        assert proof['completed_targets'] == ['control'], 'fuzz_target_incomplete'
                else:
                    assert build['fuzz_executed'] is False
                assert record['client_delivery_allowed'] is False
                if negative:
                    row = next(r for r in build['stages'] if r['id'] == 'baseline-unit')
                    assert row['status'] == 'failed' and row['exit_code'] == 8
                    assert row['executed_tests'] == ['negative'] and row['passed_tests'] == []
                    for language in ('en', 'es-MX'):
                        evidence['stage'] = 'report_' + language
                        retain()
                        evidence['reports'].append(render_result(result, args.output, language))
                        retain()
        evidence.update(status='PASS_OWNED_PROJECT_INTEGRATION', stage='completed')
    except Exception as exc:
        # The owned proof may expose an assertion name, never arbitrary tool/transport text.
        evidence['error_type'] = type(exc).__name__
        if isinstance(exc, AssertionError) and str(exc).replace('_', '').isalnum():
            evidence['failed_predicate'] = str(exc)
        raise
    finally:
        retain()
        print(json.dumps({k: evidence[k] for k in ('status', 'duration_ms', 'production_qualified', 'bitcoin_executed')}))


if __name__ == '__main__':
    main()
