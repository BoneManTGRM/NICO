"""Bounded, synthetic-only diagnostic for the production locale-render path.

No assessment is started. Private retained inputs require separate verified ZIP,
manifest and identity admission before this profiler may be used with them.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import logging
from pathlib import Path
import pstats
import resource
import subprocess
import sys
import time


def category(filename: str, name: str) -> str:
    if filename.endswith('/copy.py') or name in {'copy', 'deepcopy', '__deepcopy__'}:
        return 'copying'
    if 'pypdf' in filename and ('extract' in name or name == 'get_text'):
        return 'pdf_extraction'
    if any(part in name.lower() for part in ('walk', 'recursive', 'traverse')):
        return 'recursive_traversal'
    if any(part in filename for part in ('spanish', 'localiz', 'locale')):
        return 'localization'
    return 'other'


def summarize(profile: cProfile.Profile) -> dict:
    groups = {}
    functions = []
    for (filename, line, name), (primitive, calls, own, inclusive, _) in pstats.Stats(profile).stats.items():
        group = category(filename, name)
        counts = groups.setdefault(group, {'calls': 0, 'recursive_calls': 0, 'self_cpu_seconds': 0.0})
        counts['calls'] += calls
        counts['recursive_calls'] += calls - primitive
        counts['self_cpu_seconds'] += own
        functions.append({'file': Path(filename).name, 'line': line, 'function': name,
                          'calls': calls, 'recursive_calls': calls - primitive,
                          'self_cpu_seconds': own, 'inclusive_cpu_seconds': inclusive,
                          'category': group})
    return {'categories': groups,
            'top_self_cpu': sorted(functions, key=lambda row: row['self_cpu_seconds'], reverse=True)[:40],
            'top_inclusive_cpu': sorted(functions, key=lambda row: row['inclusive_cpu_seconds'], reverse=True)[:40],
            'inclusive_times_overlap': True,
            'categories_are_function_name_heuristics': True}


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def worker(cpu_seconds: int) -> dict:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico import comprehensive_same_run_locale_report_v1 as locale
    from nico.comprehensive_spanish_final_report_runtime_cache_v94 import reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests as reset
    from nico.report_delivery_timing_v1 import report_delivery_timing
    from pypdf import PdfReader

    # Fixture preparation is outside the render profile, but within process limits.
    status = _fixed_status('en')
    before = digest(status)
    truth = digest(locale._assessment_truth_projection(status['reports']['json']))
    phases = []

    class PhaseCapture(logging.Handler):
        def emit(self, record):
            message = record.getMessage()
            if message.startswith('NICO_REPORT_TIMING='):
                phases.append(json.loads(message.split('=', 1)[1]))

    def observe(profile=None):
        reset()
        handler = PhaseCapture()
        logger = logging.getLogger('uvicorn.error')
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        start, cpu = time.perf_counter(), time.process_time()
        try:
            if profile is not None:
                profile.enable()
            with report_delivery_timing(status['run_id'], 'es-MX'):
                response = locale.build_same_run_locale_pdf_response(status, 'es-MX')
            render = {'wall_seconds': time.perf_counter() - start, 'cpu_seconds': time.process_time() - cpu}
            extraction_start, extraction_cpu = time.perf_counter(), time.process_time()
            reader = PdfReader(io.BytesIO(response.body))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            extraction = {'wall_seconds': time.perf_counter() - extraction_start,
                          'cpu_seconds': time.process_time() - extraction_cpu}
        finally:
            if profile is not None:
                profile.disable()
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        pdf_hash = hashlib.sha256(response.body).hexdigest()
        assert response.status_code == 200
        for key, expected in {
            'x-nico-artifact-sha256': pdf_hash, 'x-nico-pdf-sha256': pdf_hash,
            'x-nico-run-id': status['run_id'], 'x-nico-commit-sha': status['commit_sha'],
            'x-nico-canonical-truth-sha256': status['reports']['canonical_truth_sha256'],
            'x-nico-report-language': 'es-MX', 'x-nico-assessment-rerun': 'false',
            'x-nico-approval-status': 'pending_human_approval',
            'x-nico-delivery-status': 'blocked_pending_human_approval',
            'x-nico-client-delivery-allowed': 'false',
        }.items():
            assert response.headers[key] == expected, key
        assert digest(status) == before
        assert digest(locale._assessment_truth_projection(status['reports']['json'])) == truth
        return {'pdf_sha256': pdf_hash, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'pages': len(reader.pages), 'bytes': len(response.body)}, render, extraction

    baseline, baseline_render, _ = observe()
    profile = cProfile.Profile(timer=time.process_time_ns, timeunit=1e-9)
    observed, render, extraction = observe(profile)
    assert observed == baseline, 'Profiling changed PDF bytes, text, or pagination'
    return {'scope': 'owned_synthetic_only', 'production_delay_fixed': False,
            'profile_scope': 'Spanish route plus separately timed verification PDF extraction',
            'input_unchanged': True, 'input_sha256': before, 'truth_unchanged': True,
            'pdf_observation': observed, 'baseline_render': baseline_render,
            'profiled_render': render, 'profiled_extraction': extraction,
            'route_phases': phases, 'profile': summarize(profile)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=int, default=120)
    parser.add_argument('--cpu-seconds', type=int, default=100)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.wall_seconds <= 600 or not 1 <= args.cpu_seconds <= 600:
        parser.error('Wall and CPU bounds must be between 1 and 600 seconds')
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error('Choose a new output path; existing evidence is never overwritten')
    if args.worker:
        result = worker(args.cpu_seconds)
        with args.output.open('x') as output:
            output.write(json.dumps(result, indent=2) + '\n')
        return
    # No stdout/stderr bodies or input data are persisted on failure.
    try:
        result = subprocess.run([sys.executable, '-m', 'scripts.profile_ordinary_spanish_render',
                                 '--worker', '--output', str(args.output),
                                 '--cpu-seconds', str(args.cpu_seconds)],
                                cwd=Path(__file__).resolve().parents[1],
                                timeout=args.wall_seconds, capture_output=True)
    except subprocess.TimeoutExpired:
        raise SystemExit('Profile exceeded wall-time bound; no successful result claimed')
    if result.returncode:
        raise SystemExit(f'Profile worker failed or exceeded CPU bound (exit {result.returncode})')
    print('Synthetic render profile verified: ' + str(args.output))


if __name__ == '__main__':
    main()
