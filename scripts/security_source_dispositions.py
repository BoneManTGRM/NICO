"""Exact reviewed redacted-metadata occurrences, not hidden-value authentication.

The source-blob hashes in the pinned review manifest record the audit's provenance.
They do not authenticate a supplied scanner report or authorize other occurrences.
Malformed/incomplete captures receive no NEW approvals; existing gate policy owns
all other dispositions and enforcement. This module never logs input values.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re

LIMIT = 4 * 1024 * 1024
MAX_FINDINGS = 110  # Reviewed identity capture bound; legacy triage stays unchanged.
MANIFEST = Path(__file__).with_name('security_source_dispositions') / 'reviewed-occurrences-v1.json'
MANIFEST_SHA256 = '197f042e3e93dce2cdb37e4c82fc666a5b2740a2c9a74a4d7944844a9c864b10'
REQUIRED = frozenset({'Commit', 'File', 'RuleID', 'StartLine', 'EndLine',
                      'StartColumn', 'EndColumn', 'Fingerprint', 'Match', 'Secret'})
OPTIONAL_TEXT = frozenset({'Description', 'Author', 'Email', 'Date', 'Message', 'SymlinkFile', 'Link'})


def _require(condition):
    if not condition:
        raise ValueError('invalid_source_disposition_capture')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_read(path, limit=LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        _require(0 < len(raw) <= limit and len(raw) == before.st_size
                 and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                 == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        return raw
    finally:
        os.close(fd)


def _decode(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= LIMIT)
    def unique_pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result)
            result[key] = value
        return result
    def reject_constant(_):
        raise ValueError('invalid_source_disposition_capture')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def _text(value, limit):
    _require(type(value) is str and len(value.encode('utf-8')) <= limit)
    return value


def _identity(finding):
    _require(type(finding) is dict and REQUIRED <= set(finding)
             and set(finding) <= REQUIRED | OPTIONAL_TEXT | {'Entropy', 'Tags'})
    # Verified is not allowed, even when false/null/zero.
    commit = _text(finding['Commit'], 40)
    _require(re.fullmatch('[0-9a-f]{40}', commit) is not None)
    path = _text(finding['File'], 4096)
    rule = _text(finding['RuleID'], 256)
    _require(path and not path.startswith('/') and '\\' not in path
             and all(part not in ('', '.', '..') for part in path.split('/'))
             and all(ord(char) >= 32 for char in path))
    _require(rule and all(ord(char) >= 32 for char in rule))
    positions = tuple(finding[key] for key in ('StartLine', 'EndLine', 'StartColumn', 'EndColumn'))
    _require(all(type(value) is int and 1 <= value <= 10**9 for value in positions))
    start, end, first, last = positions
    _require(end >= start and (end != start or last >= first))
    fingerprint = _text(finding['Fingerprint'], 8192)
    _require(fingerprint == f'{commit}:{path}:{rule}:{start}')
    _require(type(finding['Secret']) is str and finding['Secret'] == 'REDACTED')
    match = _text(finding['Match'], 65536)
    _require('REDACTED' in match)
    for key in OPTIONAL_TEXT & finding.keys():
        _text(finding[key], LIMIT if key == 'Message' else 16384)
    if 'Entropy' in finding:
        entropy = finding['Entropy']
        _require(type(entropy) in (int, float) and math.isfinite(entropy) and 0 <= entropy <= 100)
    if 'Tags' in finding:
        tags = finding['Tags']
        _require(type(tags) is list and len(tags) <= 128)
        for tag in tags:
            _text(tag, 256)
    occurrence = (commit, path, rule, *positions)
    shape = [*occurrence, fingerprint, _digest(match.encode('utf-8')), 'REDACTED', 'verified_absent']
    return occurrence, (_digest(fingerprint.encode('utf-8')), _digest(_canonical(shape)))


def _approved_bindings():
    raw = _bounded_read(MANIFEST, 65536)
    _require(_digest(raw) == MANIFEST_SHA256)
    value = _decode(raw)
    _require(value['schema'] == 'nico.review-only-source-disposition-proposal.v1')
    entries = value['entries']
    _require(type(entries) is list and len(entries) == 23)
    identities = set()
    for entry in entries:
        _require(entry['classification'] == 'recomputed_analyzer_source_digest'
                 and entry['proposed_disposition'] == 'approved_public_source_hash')
        pair = (entry['fingerprint_sha256'], entry['shape_sha256'])
        _require(all(type(part) is str and re.fullmatch('[0-9a-f]{64}', part) for part in pair))
        _require(pair not in identities)
        identities.add(pair)
    _require(len({pair[0] for pair in identities}) == 22)
    return frozenset(identities)


def approved_indices(raw_report, raw_summary, findings, summary):
    """Return only exact reviewed indices from a fully validated matching capture.

    Canonical byte comparison preserves JSON type distinctions (e.g. bool/int)
    when binding the bounded second read to the gate's original parsed snapshot.
    """
    try:
        parsed = _decode(raw_report)
        captured_summary = _decode(raw_summary)
        _require(type(parsed) is list and len(parsed) <= MAX_FINDINGS)
        _require(type(captured_summary) is dict and set(captured_summary) == {
            'scanner', 'status', 'finding_count', 'artifact_present', 'history_depth', 'exit_code'})
        _require(captured_summary['scanner'] == 'gitleaks' and captured_summary['status'] == 'completed'
                 and captured_summary['artifact_present'] is True and captured_summary['history_depth'] == 'full')
        _require(type(captured_summary['finding_count']) is int and captured_summary['finding_count'] == len(parsed))
        _require(type(captured_summary['exit_code']) is int
                 and captured_summary['exit_code'] == (1 if parsed else 0))
        _require(_canonical(parsed) == _canonical(findings)
                 and _canonical(captured_summary) == _canonical(summary))
        approved = _approved_bindings()
        seen = set()
        indices = set()
        for index, finding in enumerate(parsed):
            occurrence, identity = _identity(finding)
            _require(occurrence not in seen)
            seen.add(occurrence)
            if identity in approved:
                indices.add(index)
        return frozenset(indices)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError, OSError):
        return frozenset()


def approved_indices_from_files(root, findings, summary):
    try:
        report = _bounded_read(root / 'gitleaks.json')
        captured_summary = _bounded_read(root / 'gitleaks-summary.json')
    except (OSError, ValueError):
        return frozenset()
    return approved_indices(report, captured_summary, findings, summary)
