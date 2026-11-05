"""Optional exact-source handler syntax; never completion or a disposition.

Only trusted scanner capture supplies observations. Candidate-authored proofs
are ignored. Reads requalify receipts against retained capture without parsing.
"""
import ast
from collections.abc import Mapping
import hashlib
import json
import re

VERSION = 'nico.exception-handler-evidence.v1'
CAPTURE_VERSION = 'nico.exception-handler-observations.v1'
CAPTURE_FIELD = 'exception_handler_observations'
CAPTURE_MAX_BYTES = 4096  # Within the existing workspace envelope reservation.
MAX_LINES = 32
MAX_NODES = 10000
RECEIPT_MAX_BYTES = 2048
RECEIPT_TOTAL_BYTES = 65536
RECEIPT_COUNT_LIMIT = 64
RULE_BODIES = {'B110': 'single_pass', 'B112': 'single_continue'}
SCOPE_KEYS = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')


def encoded_size(value):
    return len(json.dumps(value, sort_keys=True, ensure_ascii=True).encode('utf-8'))


def eligible(row):
    rule = (row.get('rule_id') or row.get('rule')) if isinstance(row, Mapping) else None
    return (isinstance(row, Mapping) and row.get('category') == 'static'
            and (row.get('scanner') or row.get('tool')) == 'bandit'
            and isinstance(rule, str) and rule in RULE_BODIES
            and type(row.get('line')) is int and row['line'] > 0)


def observe_tree(tree, lines, *, clock, deadline):
    """After baseline capture, inspect one already parsed AST with bounded work.

Only ordinary except handlers with exactly one Pass/Continue are described.
Continue requires a containing loop body without a function/class boundary.
No identifiers, arguments, exception names or source text leave this helper.
    """
    if not isinstance(tree, ast.Module) or len(lines) > MAX_LINES:
        return None
    handlers, seen = {}, set()
    pending = [(tree, None, False)]
    count = 0
    while pending:
        if clock() >= deadline or count >= MAX_NODES:
            return None
        node, parent, in_loop = pending.pop()
        count += 1
        if isinstance(node, ast.ExceptHandler) and node.lineno in lines:
            if node.lineno in seen:
                return None
            seen.add(node.lineno)
            if type(parent) is ast.Try and len(node.body) == 1:
                body = node.body[0]
                if type(body) is ast.Pass:
                    handlers[str(node.lineno)] = 'single_pass'
                elif type(body) is ast.Continue and in_loop:
                    handlers[str(node.lineno)] = 'single_continue'
        for child in ast.iter_child_nodes(node):
            loop = in_loop
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                loop = False
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)) and child in node.body:
                loop = True
            pending.append((child, node, loop))
    return handlers if clock() < deadline else None


def make_capture(path, observation, handlers):
    """Build a compact sidecar only; the original observation remains unchanged."""
    from nico.candidate_source_reason_detail_v1 import path_digest
    key = path_digest(path)
    binding = observation.get('source_binding')
    if (not key or not handlers or not isinstance(binding, Mapping)
            or observation.get('status') != 'parsed' or observation.get('complete_source_blob') is not True
            or observation.get('parse_warning_count') != 0):
        return None
    value = {'artifact_schema': CAPTURE_VERSION, 'paths': {key: {
        'source_sha256': observation.get('source_sha256'), 'blob_oid': binding.get('blob_oid'),
        'handlers': dict(handlers)}}}
    return value if encoded_size(value) <= CAPTURE_MAX_BYTES else None


def _qualify(row, capture, scope):
    from nico.candidate_source_observations_v1 import candidate_source_path
    from nico.candidate_source_reason_detail_v1 import path_digest
    if (not eligible(row) or row.get('evidence_quality') != 'exact_source'
            or row.get('candidate_evidence_context_status') == 'ambiguous'
            or not isinstance(scope, Mapping) or set(scope) != set(SCOPE_KEYS)
            or not all(isinstance(scope[k], str) and 0 < len(scope[k]) <= 1024 for k in SCOPE_KEYS)
            or not re.fullmatch('[a-f0-9]{40}', scope['commit_sha'])
            or not isinstance(capture, Mapping)
            or capture.get('artifact_schema') != 'nico.persisted-candidate-investigation.v1'
            or capture.get('scope') != scope):
        return None
    path = candidate_source_path(row.get('source_path') or row.get('path'))
    if (path is None or '.git' in path.split('/')
            or row.get('exact_commit_sha') != scope['commit_sha']
            or row.get('source_commit_sha') not in (None, '', scope['commit_sha'])
            or row.get('source_repository') not in (None, '', scope['repository'])
            or any(k in row and row[k] != scope[k] for k in ('run_id', 'customer_id', 'project_id'))):
        return None
    observations = capture.get('observations')
    observed = observations.get(path) if isinstance(observations, Mapping) else None
    binding = observed.get('source_binding') if isinstance(observed, Mapping) else None
    if (not isinstance(binding, Mapping) or binding.get('repository') != scope['repository']
            or binding.get('commit_sha') != scope['commit_sha'] or binding.get('path') != path
            or binding.get('origin') is not None
            or observed.get('status') != 'parsed' or observed.get('complete_source_blob') is not True
            or type(observed.get('parse_warning_count')) is not int or observed['parse_warning_count'] != 0
            or not re.fullmatch('[a-f0-9]{40}', str(binding.get('blob_oid', '')))
            or not re.fullmatch('[a-f0-9]{64}', str(observed.get('source_sha256', '')))):
        return None
    extra = capture.get(CAPTURE_FIELD)
    if (not isinstance(extra, Mapping) or set(extra) != {'artifact_schema', 'paths'}
            or extra.get('artifact_schema') != CAPTURE_VERSION
            or not isinstance(extra.get('paths'), Mapping) or len(extra['paths']) != 1
            or encoded_size(extra) > CAPTURE_MAX_BYTES):
        return None
    item = extra['paths'].get(path_digest(path))
    if (not isinstance(item, Mapping) or set(item) != {'source_sha256', 'blob_oid', 'handlers'}
            or item.get('source_sha256') != observed['source_sha256']
            or item.get('blob_oid') != binding['blob_oid']
            or not isinstance(item.get('handlers'), Mapping) or not 0 < len(item['handlers']) <= MAX_LINES):
        return None
    for line, kind in item['handlers'].items():
        if (not isinstance(line, str) or not re.fullmatch('[1-9][0-9]{0,8}', line)
                or not isinstance(kind, str) or kind not in RULE_BODIES.values()):
            return None
    kind = item['handlers'].get(str(row['line']))
    if kind != RULE_BODIES[row.get('rule_id') or row.get('rule')]:
        return None
    value = {'version': VERSION, 'body_kind': kind, 'line': row['line'],
             'source_sha256': observed['source_sha256'], 'blob_oid': binding['blob_oid'],
             'path': path, 'scope': {k: scope[k] for k in SCOPE_KEYS},
             'candidate_input_sha256': hashlib.sha256(json.dumps(row, sort_keys=True,
                  separators=(',', ':'), default=str).encode()).hexdigest()}
    return value if encoded_size(value) <= RECEIPT_MAX_BYTES else None


def qualify(row, capture, scope):
    try:
        return _qualify(row, capture, scope)
    except (ValueError, TypeError, AttributeError, RecursionError):
        return None
