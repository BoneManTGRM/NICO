#!/usr/bin/env python3
"""Offline observations only. No network, assessment, activation or limit changes.

inventory verifies an operator-supplied archive digest and detached-manifest byte
hash, then records every member's actual bytes/hash. It does NOT infer semantic
member binding from an unknown detached-manifest schema. validate exercises only
the complete v2 family contract. write exercises the dormant path-backed writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import tracemalloc
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nico import ordinary_report_file_streams_v2 as streams
from nico import ordinary_report_files_v2 as transport

INVENTORY_BYTES = 256 * 1024 * 1024  # Diagnostic read budget, never artifact admission.


def inventory(args):
    started = time.monotonic()
    with streams._source(args.detached_manifest, transport.MAX_FAMILY_BYTES) as (source, _, _):
        _, digest, _ = streams._read(source, transport.MAX_FAMILY_BYTES, started)
    if digest != args.expected_detached_manifest_sha256:
        raise ValueError('diagnostic_detached_manifest_digest')
    with streams._source(args.archive, INVENTORY_BYTES) as (source, size, unchanged):
        _, digest, _ = streams._read(source, INVENTORY_BYTES, started)
        if digest != args.expected_archive_sha256:
            raise ValueError('diagnostic_archive_digest')
        source.seek(0)
        with zipfile.ZipFile(source) as zipped:
            infos = zipped.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or len(names) > 128:
                raise ValueError('diagnostic_member_population')
            if sum(item.file_size for item in infos) > INVENTORY_BYTES:
                raise ValueError('diagnostic_inventory_budget')
            rows, total = [], 0
            for info in infos:
                if info.flag_bits & 1 or Path(info.filename).is_absolute() or '..' in Path(info.filename).parts:
                    raise ValueError('diagnostic_unsafe_member')
                with zipped.open(info) as member:
                    count, digest, _ = streams._read(member, INVENTORY_BYTES - total, started)
                total += count
                if count != info.file_size:
                    raise ValueError('diagnostic_member_size')
                rows.append({'filename': info.filename, 'size_bytes': count, 'sha256': digest,
                             'exceeds_current_text_member_limit': count > transport.MAX_TEXT_BYTES})
        unchanged()
    return {'archive_size_bytes': size, 'members': rows, 'total_uncompressed_bytes': total,
            'exceeds_current_family_limit': total > transport.MAX_FAMILY_BYTES,
            'expected_archive_digest_verified': True, 'detached_manifest_byte_digest_verified': True,
            'detached_manifest_member_semantics_verified': False,
            'production_admission_established': False,
            'note': 'Inventory only; canonical normalization, translation, PDF/lifecycle qualification remain required.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('inventory')
    scan.add_argument('archive', type=Path)
    scan.add_argument('--expected-archive-sha256', required=True)
    scan.add_argument('--detached-manifest', type=Path, required=True)
    scan.add_argument('--expected-detached-manifest-sha256', required=True)
    check = commands.add_parser('validate')
    check.add_argument('archive', type=Path)
    check.add_argument('--identity-json', type=Path, required=True)
    check.add_argument('--expected-manifest-sha256', required=True)
    write = commands.add_parser('write')
    write.add_argument('--bundle-json', type=Path, required=True)
    write.add_argument('--identity-json', type=Path, required=True)
    write.add_argument('--expected-bundle-manifest-sha256', required=True)
    write.add_argument('--exports-directory', type=Path, required=True)
    write.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tracemalloc.start()
    status, result, code = 'complete', {}, 0
    try:
        if args.command == 'inventory': result = inventory(args)
        else:
            # Small operator-owned control files; never source network locators.
            with streams._source(args.identity_json, transport.MAX_TEXT_BYTES) as (f, _, _):
                identity = transport._json_object(streams._read(f, transport.MAX_TEXT_BYTES, started, retain=True)[2])
            if args.command == 'validate':
                result = streams.validate_report_files_zip_path(args.archive, expected_identity=identity,
                    expected_manifest_sha256=args.expected_manifest_sha256)
            else:
                with streams._source(args.bundle_json, transport.MAX_FAMILY_BYTES) as (f, _, _):
                    bundle = transport._json_object(streams._read(f, transport.MAX_FAMILY_BYTES, started, retain=True)[2])
                result = streams.write_report_files_zip_from_paths(bundle,
                    {kind: args.exports_directory / name for kind, name in transport.EXPORT_NAMES.items()}, args.destination,
                    expected_identity=identity, expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        status, result, code = 'blocked', {'error': str(exc)}, 1
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(json.dumps({'status': status, 'result': result, 'elapsed_seconds': time.monotonic() - started,
        'python_tracemalloc_peak_bytes': peak, 'process_peak_rss': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'baseline_process_peak_rss': baseline_rss, 'rss_units': 'bytes' if sys.platform == 'darwin' else 'KiB',
        'canonical_parse_is_materialized': True, 'no_capacity_limits_changed': True,
        'worker_hard_limits_established': False}, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
