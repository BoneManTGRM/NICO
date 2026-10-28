"""Bounded offline Python source observations, never automatic dispositions.

Callers supply bytes from an authenticated exact-commit source object. No code is
executed and no source text, string literal, code identifier, or credential is emitted.
Output retains repository/path/commit metadata to bind each observation.
"""
import ast
import hashlib
import re
from collections.abc import Mapping

VERSION = 'nico.candidate-source-observations.v1'
MAX_SOURCE_BYTES = 1_048_576


def observe_python_source(source: bytes, *, repository: str, commit_sha: str,
                          path: str, blob_oid: str) -> dict:
    if len(source) > MAX_SOURCE_BYTES:
        return {'status': 'source_size_limit', 'statements': {}}
    # The offline loader obtains this OID from the exact commit tree, not from
    # candidate prose. Verify byte identity before parsing that tree member.
    actual_oid = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if (not re.fullmatch(r'[0-9a-f]{40}', commit_sha) or actual_oid != blob_oid
            or not repository or not path):
        return {'status': 'source_binding_invalid', 'statements': {}}
    binding = {'repository': repository, 'commit_sha': commit_sha, 'path': path, 'blob_oid': blob_oid}
    digest = hashlib.sha256(source).hexdigest()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        return {'status': 'source_parse_unavailable', 'source_sha256': digest, 'statements': {}}
    statements = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assert, ast.Import, ast.ImportFrom, ast.Call, ast.Try)):
            statements.setdefault(node.lineno, set()).add(type(node).__name__)
    return {'status': 'parsed', 'source_binding': binding, 'source_sha256': digest,
            'statements': {str(k): sorted(v) for k, v in statements.items()}}


def candidate_source_observation(candidate: Mapping, observation: Mapping, *,
                                 observed_commit: str, expected_commit: str, expected_repository: str) -> dict:
    """Describe exact-line structure; never infer safety, reachability or approval."""
    result = {'artifact_schema': VERSION, 'candidate_id': candidate.get('candidate_id'),
              'status': 'unresolved', 'observations': [], 'recommended_disposition': 'human_review_required',
              'human_review_required': True, 'client_delivery_allowed': False,
              'score_effect': 'none', 'runtime_validation_performed': False}
    if (not expected_commit or observed_commit != expected_commit
            or candidate.get('exact_commit_sha') != expected_commit
            or candidate.get('source_commit_sha') not in (None, '', expected_commit)):
        return {**result, 'reason': 'source_identity_mismatch'}
    if candidate.get('category') != 'static' or candidate.get('evidence_quality') != 'exact_source':
        return {**result, 'reason': 'unsupported_or_missing_exact_source_evidence'}
    if observation.get('status') != 'parsed':
        return {**result, 'reason': 'source_parse_unavailable'}
    binding = observation.get('source_binding')
    path = candidate.get('source_path') or candidate.get('path')
    if (not isinstance(binding, Mapping) or binding.get('commit_sha') != expected_commit
            or binding.get('repository') != expected_repository or not expected_repository
            or binding.get('path') != path
            or candidate.get('source_repository') not in (None, '', expected_repository)):
        return {**result, 'reason': 'source_file_binding_mismatch'}
    result['source_binding'] = dict(binding)
    line = candidate.get('line')
    if type(line) is not int or line < 1:
        return {**result, 'reason': 'source_line_missing'}
    kinds = observation.get('statements', {}).get(str(line), [])
    rule = candidate.get('rule_id') or candidate.get('rule')
    required_kind = {'B101': 'Assert', 'B404': 'Import', 'B405': 'Import', 'B603': 'Call', 'B607': 'Call'}.get(rule)
    if rule in {'B404', 'B405'} and 'ImportFrom' in kinds:
        required_kind = 'ImportFrom'
    if required_kind is None:
        return {**result, 'status': 'source_parsed', 'source_sha256': observation.get('source_sha256'),
                'reason': 'rule_semantics_require_specialist_review'}
    if required_kind not in kinds:
        return {**result, 'source_sha256': observation.get('source_sha256'), 'reason': 'rule_source_line_mismatch'}
    return {**result, 'status': 'structure_observed', 'source_sha256': observation.get('source_sha256'),
            'observations': [required_kind], 'reason': 'exact_line_structure_only',
            'proof_gaps': ['production_scope', 'first_party_reachability', 'supported_security_boundary',
                           'existing_mitigation_assessment', 'realistic_exploitability']}
