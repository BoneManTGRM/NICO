"""Project-execution evidence in the existing Comprehensive scanner chapter.

This is presentation of verified canonical records, not another report pipeline
or a source of coverage, score, qualification, approval, or delivery decisions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping
import re

from nico.assessment_cpp_full_project import PROFILE

from nico.comprehensive_coverage_reconciliation_v1 import COPY_ES


def enrich_scanner_stage(canonical, stage):
    from nico.v2_premium_report_renderer import _is_spanish
    records = [r for r in canonical.get('scanner_execution_records') or []
               if isinstance(r, Mapping) and isinstance(r.get('cpp_build_evidence'), Mapping)
               and r['cpp_build_evidence'].get('profile') == PROFILE]
    if not records:
        return stage
    out = deepcopy(stage)
    es = _is_spanish(canonical)
    summaries, evidence, gaps = [], [], []
    states = {'completed': 'completado', 'failed': 'falló', 'partial': 'parcial',
              'timed_out': 'tiempo agotado', 'not_attempted': 'no ejecutado'}
    labels = {'baseline': 'base', 'address': 'direcciones', 'undefined': 'comportamiento indefinido',
              'configure': 'configuración', 'build': 'compilación', 'discover': 'descubrimiento',
              'unit': 'pruebas unitarias', 'integration': 'pruebas de integración',
              'compiler-evidence': 'evidencia del compilador', 'generated-context': 'captura de encabezados generados',
              'static-analysis': 'análisis estático', 'cmake-version': 'versión de CMake',
              'compiler-version': 'versión del compilador', 'analyzer-version': 'versión del analizador',
              'native-test-evidence': 'verificación del binario de prueba'}
    for record in records:
        provenance = record.get('worker_provenance')
        provenance = provenance if isinstance(provenance, Mapping) else {}
        binding = provenance.get('identity') or {}
        identity = canonical.get('identity')
        identity = identity if isinstance(identity, Mapping) else {}
        digest = record.get('raw_artifact_sha256')
        verified = (isinstance(provenance, Mapping) and isinstance(binding, Mapping)
            and record.get('raw_artifact_retention_complete') is True
            and record.get('current_run') is True and record.get('exact_commit_match') is True
            and record.get('execution_observed_for_this_report') is True
            and provenance.get('profile') == PROFILE and isinstance(digest, str)
            and re.fullmatch(r'[0-9a-f]{64}', digest) is not None
            and provenance.get('receipt_sha256') == digest
            and bool(identity.get('run_id')) and binding.get('run_id') == identity.get('run_id')
            and bool(identity.get('commit_sha')) and binding.get('revision') == identity.get('commit_sha')
            and record.get('commit_sha') == identity.get('commit_sha'))
        if not verified:
            gaps.append('La evidencia de ejecución del proyecto C/C++ no está vinculada a un comprobante conservado y verificado de esta evaluación.' if es
                else 'C/C++ project execution evidence is not bound to a verified retained receipt for this assessment.')
            continue
        build = record['cpp_build_evidence']
        rows = [r for r in build.get('stages') or [] if isinstance(r, Mapping)]
        built = build.get('build_completed') is True
        if es:
            summaries.append('Ejecución del proyecto C/C++: compilación ' + ('completada.' if built else 'no verificada.'))
        else:
            summaries.append('C/C++ project execution: build ' + ('completed.' if built else 'not verified.'))
        for row in rows:
            key = str(row.get('id') or '')
            # Preserve machine identity separately; do not translate source/test identifiers.
            title = key
            if es:
                if key in labels: title = labels[key]
                elif '-' in key:
                    group, kind = key.split('-', 1)
                    title = labels.get(group, group) + ' / ' + labels.get(kind, kind)
            state = str(row.get('status') or 'unknown')
            shown = states.get(state, 'desconocido') if es else state
            code = row.get('exit_code')
            code_text = str(code) if type(code) is int else ('no disponible' if es else 'unavailable')
            exit_label = ('resultado del controlador=' if es else 'controller result=') if row.get('observation_kind') == 'controller' else ('salida nativa=' if es else 'native exit=')
            line = f'{title}: {shown}; ' + exit_label + code_text
            selected = row.get('required_tests')
            if isinstance(selected, list):
                executed, passed = row.get('executed_tests'), row.get('passed_tests')
                ex = str(len(executed)) if isinstance(executed, list) else ('desconocido' if es else 'unknown')
                pa = str(len(passed)) if isinstance(passed, list) else ('desconocido' if es else 'unknown')
                line += (f'; ejecutadas={ex}/{len(selected)}; aprobadas={pa}/{len(selected)}' if es
                         else f'; executed={ex}/{len(selected)}; passed={pa}/{len(selected)}')
                if key.startswith('baseline-'):
                    summaries.append(line + '.')
            evidence.append(line)
        compiler = (build.get('compiler_evidence') or {}).get('baseline')
        if isinstance(compiler, Mapping):
            required = compiler.get('required_translation_units') or []
            completed = compiler.get('compiled_translation_units') or []
            count = len(compiler.get('header_inclusions') or {})
            line = (f'Compilación directa verificada: {len(completed)}/{len(required)} unidades; encabezados originales incluidos: {count}.' if es
                    else f'Direct compiler verification: {len(completed)}/{len(required)} units; original headers included: {count}.')
            summaries.append(line)
            evidence.append(line)
            evidence.append('Los símbolos de los objetos compilados no verifican la instrumentación de los ejecutables de las pruebas.' if es
                            else 'Compiled-object symbols do not verify instrumentation of the test executables.')
        for group, proof in (build.get('native_test_binary_evidence') or {}).items():
            if not isinstance(proof, Mapping): continue
            required = len(proof.get('required_tests') or [])
            bound = len(proof.get('binary_bound_tests') or [])
            passed = len(proof.get('passed_tests') or [])
            line = (f'Repeticiones aisladas de binarios / {labels.get(group, group)}: {bound}/{required} vinculadas; {passed}/{required} aprobadas.' if es
                    else f'Isolated binary replays / {group}: {bound}/{required} bound; {passed}/{required} passed.')
            summaries.append(line)
            evidence.append(line)
            for outcome in proof.get('native_outcomes') or []:
                name = str(outcome.get('name') or '')
                code = outcome.get('exit_code')
                timed_out = outcome.get('timed_out') is True
                evidence.append((f'Prueba aislada / {labels.get(group, group)} / {name}: salida nativa={code}; tiempo agotado=' + ('sí' if timed_out else 'no') + '.' if es
                    else f'Isolated test / {group} / {name}: native exit={code}; timed out=' + ('yes' if timed_out else 'no') + '.'))
        context = (build.get('generated_context') or {}).get('baseline')
        if isinstance(context, Mapping):
            captured = context.get('captured_header_hashes') or {}
            included = compiler.get('generated_header_inclusions') or {} if isinstance(compiler, Mapping) else {}
            line = (f'Encabezados generados: {len(captured)} capturados; {len(included)} incluidos en la compilación directa. No son archivos originales del repositorio.' if es
                    else f'Generated headers: {len(captured)} captured; {len(included)} included by direct compilation. These are not original repository files.')
            summaries.append(line)
            evidence.append(line)
            digest = context.get('capture_sha256')
            if isinstance(digest, str):
                evidence.append(('SHA-256 de la captura de encabezados generados: ' if es else 'Generated-header capture SHA-256: ') + digest)
        header_verified = (record.get('cppcheck_source_coverage') or {}).get('header_context_verified') is True
        if es:
            gaps.append('La ejecución de libFuzzer no está verificada; la calificación integral sigue incompleta.' if header_verified else
                'La ejecución de libFuzzer y la cobertura de inclusión de encabezados no están verificadas; la calificación integral sigue incompleta.')
            gaps.append('La pertenencia a la base de datos de compilación no demuestra cobertura de ejecución del compilador. La finalización de Cppcheck no implica pruebas aprobadas ni aprobación humana.')
        else:
            gaps.append('LibFuzzer execution is not verified; full-project qualification remains incomplete.' if header_verified else
                'LibFuzzer execution and header inclusion coverage are not verified; full-project qualification remains incomplete.')
            gaps.append('Compilation database membership is not compiler execution coverage. Cppcheck completion does not imply passing tests or human approval.')
        peak = build.get('memory_peak_bytes')
        if type(peak) is int:
            evidence.append(('Pico de memoria del contenedor: ' if es else 'Container memory peak: ') + str(peak) + ' bytes.')
    has_replays = any(isinstance(r['cpp_build_evidence'].get('native_test_binary_evidence'), Mapping) for r in records)
    if has_replays:
        from nico.assessment_cpp_native_tests import ORIGINAL_CTEST_LIMIT
        gaps.append(COPY_ES[ORIGINAL_CTEST_LIMIT] if es else ORIGINAL_CTEST_LIMIT)
    else:
        gaps.append(COPY_ES['Sanitizer flags are verified in configuration; independent binary instrumentation is not established.'] if es
            else 'Sanitizer flags are verified in configuration; independent binary instrumentation is not established.')
    out['summary'] = ' '.join([out.get('summary', ''), *summaries])
    out['evidence'] = [*(out.get('evidence') or []), *evidence]
    out['unavailable'] = [*(out.get('unavailable') or []), *dict.fromkeys(gaps)]
    out['status'] = 'review_required'
    return out
