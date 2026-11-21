"""Install the reviewed CTU first-use cache after the pinned replacement index.

Trusted analyzer sources only; this is a production optimization, not diagnostic
instrumentation or qualification. Existing AST, grammar and observer layers stay.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

try:
    from . import patch_cppcheck_header_evidence as parser
except ImportError:  # Standalone image-build invocation.
    import patch_cppcheck_header_evidence as parser

MANIFEST_SHA256 = '38cb5a984aff81d89b54bc597f851db231cff90180bd5c84b962502608718fe6'
PARSER_SHA256 = '9f3261e77b3c75154f67ed23eac5001d988ff46363ffd0cecd763e77e6d34fdc'
REPAIR_ID = 'ctu-first-use-v1'
UPSTREAM_COMMIT = 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
SOURCES = frozenset({'lib/ctu.cpp'})
PREREQUISITES = parser.SOURCES | {'lib/tokenize.cpp', 'lib/templatesimplifier.cpp',
                                   'lib/token.cpp', 'lib/tokenlist.cpp', 'lib/tokenlist.h'}
VARIANTS = frozenset({'placement-v1-grammar-v2', 'placement-v2-grammar-v3'})
PRIOR_SCRIPTS = frozenset({'repair_cppcheck_placement_ast.py', 'repair_cppcheck_header_grammar.py',
                          'patch_cppcheck_header_evidence.py', 'repair_cppcheck_replacement_index.py'})
LIMIT = 2 * 1024 * 1024


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _manifest(bundle):
    raw, _ = parser.stable(bundle / 'manifest.json', 65536)
    if parser.digest(raw) != MANIFEST_SHA256:
        raise ValueError('ctu_first_use_manifest_mismatch')
    value = json.loads(raw)
    if (set(value) != {'schema', 'repair_id', 'upstream_commit', 'base_tool_version',
                       'patch', 'patch_sha256', 'native_controls', 'native_controls_sha256',
                       'patch_parser_sha256', 'variants'} or
            value['schema'] != 'nico.cppcheck-ctu-first-use-manifest.v1' or
            value['repair_id'] != REPAIR_ID or value['upstream_commit'] != UPSTREAM_COMMIT or
            value['base_tool_version'] != '2.17.1' or
            value['patch'] != 'ctu-first-use-v1.patch' or
            value['native_controls'] != 'native-controls.cpp' or
            value['patch_parser_sha256'] != PARSER_SHA256 or
            set(value['variants']) != VARIANTS):
        raise ValueError('ctu_first_use_manifest_invalid')
    for entry in value['variants'].values():
        if (set(entry) != {'sources', 'prerequisites', 'expected_prior_repairs'} or
                set(entry['sources']) != SOURCES or set(entry['prerequisites']) != PREREQUISITES or
                set(entry['expected_prior_repairs']) != PRIOR_SCRIPTS or
                not all(_sha(x) for x in (*entry['prerequisites'].values(), *entry['expected_prior_repairs'].values()))):
            raise ValueError('ctu_first_use_manifest_invalid')
        for pair in entry['sources'].values():
            if set(pair) != {'before_sha256', 'after_sha256'} or not all(_sha(x) for x in pair.values()):
                raise ValueError('ctu_first_use_manifest_invalid')
    return value


def _stage(destination, data, mode):
    fd, name = tempfile.mkstemp(prefix='.nico-ctu-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        return name
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


def apply_repair(source, bundle):
    source, bundle = Path(source).absolute(), Path(bundle).absolute()
    if (source != source.resolve(strict=True) or not source.is_dir() or
            bundle != bundle.resolve(strict=True) or not bundle.is_dir()):
        raise ValueError('ctu_first_use_path_invalid')
    manifest = _manifest(bundle)
    parser_raw, _ = parser.stable(Path(parser.__file__))
    if parser.digest(parser_raw) != PARSER_SHA256:
        raise ValueError('ctu_first_use_parser_mismatch')
    script_raw, _ = parser.stable(Path(__file__))
    patch, _ = parser.stable(bundle / manifest['patch'], 256 * 1024)
    control, _ = parser.stable(bundle / manifest['native_controls'], 256 * 1024)
    if parser.digest(patch) != manifest['patch_sha256'] or parser.digest(control) != manifest['native_controls_sha256']:
        raise ValueError('ctu_first_use_bundle_mismatch')
    originals, modes, prerequisites = {}, {}, {}
    for name in sorted(SOURCES):
        originals[name], modes[name] = parser.stable(source / name, LIMIT)
    for name in sorted(PREREQUISITES):
        prerequisites[name], _ = parser.stable(source / name, LIMIT)
    matching = [name for name, entry in manifest['variants'].items()
                if all(parser.digest(originals[p]) == pair['before_sha256'] for p, pair in entry['sources'].items())
                and all(parser.digest(prerequisites[p]) == sha for p, sha in entry['prerequisites'].items())]
    if len(matching) != 1:
        raise ValueError('ctu_first_use_source_variant_mismatch')
    variant = matching[0]
    entry = manifest['variants'][variant]
    results = parser.patched_sources(patch, originals)
    if set(results) != SOURCES or any(not 0 < len(raw) <= LIMIT or
            parser.digest(raw) != entry['sources'][name]['after_sha256'] for name, raw in results.items()):
        raise ValueError('ctu_first_use_output_mismatch')
    prepared, backups, committed = {}, {}, []
    try:
        for name in sorted(SOURCES):
            prepared[name] = _stage(source / name, results[name], modes[name])
            backups[name] = _stage(source / name, originals[name], modes[name])
        if any(parser.stable(source / name)[0] != raw for name, raw in {**originals, **prerequisites}.items()):
            raise ValueError('ctu_first_use_source_changed')
        try:
            for name in sorted(SOURCES):
                if parser.stable(source / name)[0] != originals[name]:
                    raise ValueError('ctu_first_use_source_changed')
                os.replace(prepared[name], source / name)
                committed.append(name)
            if any(parser.stable(source / name)[0] != raw for name, raw in {**results, **prerequisites}.items()):
                raise ValueError('ctu_first_use_output_changed')
        except BaseException:
            # Restore only files we replaced and still own; never overwrite a
            # concurrently changed file. No receipt is emitted on any failure.
            for name in reversed(committed):
                if parser.stable(source / name)[0] != results[name]:
                    raise ValueError('ctu_first_use_restore_conflict')
                os.replace(backups[name], source / name)
            raise
    finally:
        for temporary in (*prepared.values(), *backups.values()):
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'schema': 'nico.cppcheck-ctu-first-use-repair.v1', 'repair_id': REPAIR_ID,
            'variant': variant, 'manifest_sha256': MANIFEST_SHA256,
            'application_script_sha256': parser.digest(script_raw), 'patch_parser_sha256': PARSER_SHA256,
            'patch_sha256': manifest['patch_sha256'], 'native_controls_sha256': manifest['native_controls_sha256'],
            'upstream_commit': UPSTREAM_COMMIT, 'base_tool_version': '2.17.1',
            'sources': entry['sources'], 'prerequisites': entry['prerequisites'],
            'expected_prior_repairs': entry['expected_prior_repairs'], 'native_qualification_completed': False}


def main():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument('source', type=Path)
    command.add_argument('bundle', type=Path)
    args = command.parse_args()
    print(json.dumps(apply_repair(args.source, args.bundle), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
