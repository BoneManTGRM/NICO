"""Bounded structural projection of the pinned Semgrep 1.170.0 JSON contract.

Source: https://raw.githubusercontent.com/semgrep/semgrep/v1.170.0/cli/src/semgrep/semgrep_interfaces/semgrep_output_v1.py
SHA256: 54f031e27a17e6a3dcb640b4719bc5be6395891b54ca07b6d5e1106c91e6061b
CliError, ErrorType, ErrorSeverity, Location, Position and ErrorSpan are the
source contracts. Category aggregation is our fixed interpretation of explicit
machine variants, never message classification. Group equality concerns selected
structural metadata, not semantic duplication. No source path is opened.
"""
from collections import Counter
import hashlib
import json

SCHEMA_SHA256 = '54f031e27a17e6a3dcb640b4719bc5be6395891b54ca07b6d5e1106c91e6061b'
# Pinned error.py SHA256 94220dbdd3e7e699b1aa87f6cc7e102518d8cc1366f4bbbecdebcf3cee4e5a23
# Published (non-commented) exit constants only; no meaning inferred from code.
EXIT_CODES = frozenset({0, 1, 2, 3, 4, 5, 7, 8, 13})
CATEGORIES = ('parse', 'lexical', 'timeout', 'resource', 'unsupported', 'configuration', 'internal', 'unknown')
SEVERITIES = ('error', 'warning', 'info', 'unknown', 'missing')
# Exact JSON names, not OCaml/Python constructor names.
TYPES = {
    'Lexical error': 'lexical', 'Syntax error': 'parse',
    'Other syntax error': 'parse', 'AST builder error': 'parse',
    'Rule parse error': 'configuration', 'SemgrepWarning': 'unknown',
    'SemgrepError': 'unknown', 'InvalidRuleSchemaError': 'configuration',
    'UnknownLanguageError': 'unsupported', 'Invalid YAML': 'configuration',
    'Internal matching error': 'internal', 'Semgrep match found': 'unknown',
    'Too many matches': 'resource', 'Fatal error': 'unknown',
    'Timeout': 'timeout', 'Out of memory': 'resource',
    'Fixpoint timeout': 'timeout', 'Stack overflow': 'resource',
    'Timeout during interfile analysis': 'timeout',
    'OOM during interfile analysis': 'resource', 'Missing plugin': 'unsupported',
    'Pattern parse error': 'configuration', 'Incompatible rule': 'unsupported',
}


def text(value, limit=16384):
    if type(value) is not str or not value or len(value.encode('utf-8')) > limit:
        raise ValueError('invalid')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('invalid')
    return value


def path(value, tracked_paths):
    value = text(value)
    if value.startswith('/') or '\\' in value or ':' in value:
        raise ValueError('invalid')
    parts = value.split('/')
    if any(part in ('', '..') for part in parts):
        raise ValueError('invalid')
    parts = [part for part in parts if part != '.']
    if not parts:
        raise ValueError('invalid')
    result = '/'.join(parts)
    if result not in tracked_paths:
        raise ValueError('unbound')
    return result


def position(value):
    if type(value) is not dict or not {'line', 'col'} <= value.keys():
        raise ValueError('invalid')
    result = [value['line'], value['col'], value.get('offset', 0)]
    if any(type(number) is not int for number in result):
        raise ValueError('invalid')
    if not all(1 <= number <= 10**9 for number in result[:2]) or not -1 <= result[2] <= 10**9:
        raise ValueError('invalid')
    return result


def location(value, tracked_paths, key='path'):
    if type(value) is not dict:
        raise ValueError('invalid')
    start, end = position(value['start']), position(value['end'])
    if end[:2] < start[:2] or (start[2] >= 0 and end[2] >= 0 and end[2] < start[2]):
        raise ValueError('invalid')
    return [text(value[key]) if tracked_paths is None else path(value[key], tracked_paths), start, end]


def span(value, tracked_paths):
    base = location(value, tracked_paths, 'file')
    extras = []
    for key in ('config_start', 'config_end', 'context_start', 'context_end'):
        extras.append(position(value[key]) if value.get(key) is not None else None)
    selector = value.get('config_path')
    if selector is not None:
        if type(selector) is not list or len(selector) > 128:
            raise ValueError('invalid')
        selector = [text(item, 256) for item in selector]
    return [base, extras, selector]


def machine_type(value, tracked_paths):
    if type(value) is str and value in TYPES:
        return value, TYPES[value], []
    if type(value) is list and len(value) == 2:
        name, payload = value
        if name == 'PartialParsing' and type(payload) is list and len(payload) <= 2048:
            return name, 'parse', [location(item, None) for item in payload]
        if name == 'PatternParseError' and type(payload) is list and len(payload) <= 128:
            # The YAML selector is not an error message, but is not projected.
            for item in payload:
                text(item, 256)
            return name, 'configuration', [['yaml_selector', payload]]
    # Other algebraic variants have nested contracts not used by this projection.
    # Never hash or export unknown constructor names or payloads.
    raise ValueError('unknown')


def project(errors, version, tracked_paths):
    categories = Counter({name: 0 for name in CATEGORIES})
    severities = Counter({name: 0 for name in SEVERITIES})
    groups = Counter()
    recognized = 0
    ungrouped = 0
    for error in errors:
        level = error.get('level') if type(error) is dict else None
        severity = {'error': 'error', 'warn': 'warning', 'info': 'info'}.get(level, 'unknown') if type(level) is str else 'unknown'
        if version != '1.170.0':
            severity = 'unknown'
        if type(error) is dict and 'level' not in error:
            severity = 'missing'
        severities[severity] += 1
        try:
            if version != '1.170.0' or type(error) is not dict:
                raise ValueError('unknown')
            name, category, locations = machine_type(error.get('type'), tracked_paths)
        except (ValueError, KeyError, TypeError, UnicodeError):
            categories['unknown'] += 1
            ungrouped += 1
            continue
        recognized += 1
        categories[category] += 1
        try:
            if name == 'PartialParsing':
                locations = [location(item, tracked_paths) for item in error['type'][1]]
            code = error.get('code')
            if type(code) is not int or code not in EXIT_CODES or severity in ('unknown', 'missing'):
                raise ValueError('invalid')
            rule = text(error['rule_id']) if 'rule_id' in error else None
            source = path(error['path'], tracked_paths) if 'path' in error else None
            spans = error.get('spans', [])
            if type(spans) is not list or len(spans) > 2048:
                raise ValueError('invalid')
            spans = [span(item, tracked_paths) for item in spans]
            if not (rule or source or locations or spans):
                raise ValueError('unavailable')
            # Preserve range order/multiplicity; messages, help and snippets excluded.
            identity = ['semgrep-structural-v1', name, severity, code, rule, source, locations, spans]
            digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            groups[(digest, category, severity)] += 1
        except (ValueError, KeyError, TypeError, UnicodeError):
            ungrouped += 1
    return [
        {'record': 'semgrep_categories', 'mapping': 'pinned_1_170_0', 'schema_sha256': SCHEMA_SHA256,
         'recognized_entries': recognized, **categories},
        {'record': 'semgrep_severities', 'basis': 'pinned_error_severity', **severities},
        {'record': 'semgrep_groups', 'state': 'structural_metadata', 'reported_entries': len(errors),
         'grouped_entries': sum(groups.values()), 'ungrouped_entries': ungrouped,
         'group_count': len(groups), 'semantic_deduplication': False, 'path_binding': 'head_regular_blob_membership'},
        *[{'record': 'semgrep_group', 'index': index, 'shape_sha256': digest,
           'category': category, 'severity': severity, 'occurrences': count}
          for index, ((digest, category, severity), count) in enumerate(sorted(groups.items()))],
    ]
