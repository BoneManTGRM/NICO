"""Physical membership observed inside the pinned Clang analyzer pass.

Parsed AST membership, syntax-body callbacks and whole-TU completion are
distinct observations. None establish individual-checker or path/line coverage.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re

CLANG_HEADER_SCHEMA = 'nico.clang-header-observer.v1'
CLANG_HEADER_LIMIT = 1024 * 1024
CLANG_HEADER_MANIFEST_SHA256 = 'b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8'
CLANG_HEADER_SOURCE_SHA256 = '76ad9e51e0500a6d93fc81038ca7df6cb42c14d8d580b42f92b1281efa7124a1'
CLANG_HEADER_SDK_SHA256 = '76385517f23a58851167a04ef5ba1697830fe62e569acdf804eec708e063260b'
CLANG_HEADER_RUNTIME_SHA256 = '57c8fa1fb9dabce9c7e3f546ccb7d6fb549abece632742448272e10fabb66abb'


def _clang_require(condition):
    if not condition:
        raise ValueError('worker_clang_header_evidence_invalid')


def _clang_json(raw, limit):
    _clang_require(isinstance(raw, bytes) and 0 < len(raw) <= limit)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _clang_require(key not in result)
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=unique,
            parse_constant=lambda unused: _clang_require(False))
    except (ValueError, UnicodeError) as error:
        raise ValueError('worker_clang_header_evidence_invalid') from error


def validate_clang_header_tool_receipt(raw):
    value = _clang_json(raw, 65536)
    _clang_require(isinstance(value, dict) and set(value) == {'schema', 'manifest_sha256',
        'source_sha256', 'sdk_lock_sha256', 'runtime_lock_sha256', 'clang_version',
        'plugin_sha256', 'compiler_version', 'qualification_completed'})
    _clang_require(value['schema'] == 'nico.clang-header-tool.v1'
        and value['manifest_sha256'] == CLANG_HEADER_MANIFEST_SHA256
        and value['source_sha256'] == CLANG_HEADER_SOURCE_SHA256
        and value['sdk_lock_sha256'] == CLANG_HEADER_SDK_SHA256
        and value['runtime_lock_sha256'] == CLANG_HEADER_RUNTIME_SHA256
        and value['clang_version'] == '17.0.6' and value['compiler_version'] == '14.2.0'
        and isinstance(value['plugin_sha256'], str)
        and re.fullmatch(r'[0-9a-f]{64}', value['plugin_sha256']) is not None
        and value['qualification_completed'] is False)
    return value


def validate_clang_header_trace(raw, *, source, context_id, locations, standard):
    """Rebind physical paths to immutable bytes; retain incomplete native state."""
    _clang_require(isinstance(locations, dict) and source in locations
        and isinstance(context_id, str) and re.fullmatch(r'[0-9a-f]{64}', context_id) is not None)
    value = _clang_json(raw, CLANG_HEADER_LIMIT)
    fields = {'schema', 'clang_version', 'source', 'standard', 'context_id',
        'translation_unit_started', 'translation_unit_ended', 'diagnostic_errors',
        'observation_overflow', 'files'}
    _clang_require(isinstance(value, dict) and set(value) == fields
        and value['schema'] == CLANG_HEADER_SCHEMA and value['clang_version'] == '17.0.6'
        and value['source'] == source and value['context_id'] == context_id
        and value['standard'] == standard and isinstance(value['files'], list)
        and len(value['files']) <= 4096)
    for key in ('translation_unit_started', 'translation_unit_ended', 'diagnostic_errors', 'observation_overflow'):
        _clang_require(type(value[key]) is bool)
    _clang_require(not value['translation_unit_ended'] or value['translation_unit_started'])
    entered, parsed, body, rows, seen, path_bytes = [], [], [], [], set(), 0
    for row in value['files']:
        _clang_require(isinstance(row, dict) and set(row) == {'path', 'entered', 'ast_decl_nodes',
            'ast_stmt_nodes', 'ast_body_callbacks', 'initially_system', 'system_header_pragma_observed'})
        path = row['path']
        _clang_require(isinstance(path, str) and path.startswith('/') and len(path) <= 4096
            and not path.startswith('//') and '\x00' not in path and path not in seen)
        normalized = posixpath.normpath(path)
        roots = ('/work/source', '/work/analysis/generated-baseline')
        owned = any(spelling == root or spelling.startswith(root + '/')
            for spelling in (path, normalized) for root in roots)
        # FileEntry preserves ordinary GCC include spellings containing '..'.
        # Keep those raw external observations without granting input coverage.
        # Either spelling entering an owned tree requires an exact binding.
        _clang_require(normalized != '/' and (not owned or (
            path == normalized and path in locations)))
        seen.add(path); path_bytes += len(path.encode('utf-8'))
        _clang_require(path_bytes <= 512 * 1024)
        for key in ('entered', 'ast_decl_nodes', 'ast_stmt_nodes', 'ast_body_callbacks'):
            _clang_require(type(row[key]) is int and 0 <= row[key] < 2**63)
        for key in ('initially_system', 'system_header_pragma_observed'):
            _clang_require(type(row[key]) is bool)
        _clang_require(not row['ast_body_callbacks'] or row['ast_decl_nodes'] or row['ast_stmt_nodes'])
        _clang_require(not (row['ast_decl_nodes'] or row['ast_stmt_nodes'] or row['ast_body_callbacks'])
            or (row['entered'] > 0 and value['translation_unit_started']))
        # Owned input paths must be captured. External toolchain files remain
        # raw observations, without repository/header coverage credit.
        _clang_require(path in locations or not path.startswith(('/work/source/', '/work/analysis/generated-baseline/')))
        if path not in locations:
            continue
        binding = locations[path]
        _clang_require(isinstance(binding, (tuple, list)) and len(binding) == 3
            and binding[0] in {'original', 'generated'} and isinstance(binding[2], str)
            and re.fullmatch(r'[0-9a-f]{64}', binding[2]) is not None)
        if row['entered']: entered.append(path)
        if row['ast_decl_nodes'] or row['ast_stmt_nodes']: parsed.append(path)
        if row['ast_body_callbacks']: body.append(path)
        rows.append({**row, 'origin': binding[0], 'relative_path': binding[1], 'source_sha256': binding[2]})
    complete = (value['translation_unit_started'] and value['translation_unit_ended']
        and not value['diagnostic_errors'] and not value['observation_overflow']
        and source in entered)
    return {'schema': CLANG_HEADER_SCHEMA, 'context_id': context_id, 'source': source,
        'standard': standard, 'native_trace_sha256': hashlib.sha256(raw).hexdigest(),
        'include_observed_files': sorted(entered), 'parsed_ast_files': sorted(parsed),
        'syntax_body_callback_files': sorted(body), 'bound_file_observations': rows,
        'normal_pass_completed': complete,
        'translation_unit_started': value['translation_unit_started'],
        'translation_unit_ended': value['translation_unit_ended'],
        'diagnostic_errors_observed_at_emit': value['diagnostic_errors'],
        'observation_overflow': value['observation_overflow'],
        'unvisited_files': sorted(set(locations)-set(entered)),
        'analysis_method': 'clang_static_analyzer_tu_ast_observer',
        'individual_checker_coverage_verified': False, 'line_branch_coverage_verified': False}
