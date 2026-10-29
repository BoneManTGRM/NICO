"""Bounded offline Python source observations, never automatic dispositions.

Callers supply bytes from an authenticated exact-commit source object. No code is
executed and no source text, string literal, code identifier, or credential is emitted.
Output retains repository/path/commit metadata to bind each observation.
"""
import ast
import hashlib
import re
import warnings
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
        with warnings.catch_warnings(record=True) as parse_warnings:
            warnings.simplefilter('always', SyntaxWarning)
            tree = ast.parse(source)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        return {'status': 'source_parse_unavailable', 'source_sha256': digest, 'statements': {}}
    statements = {}
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assert, ast.Import, ast.ImportFrom, ast.Call, ast.Try)):
            statements.setdefault(node.lineno, set()).add(type(node).__name__)
        if isinstance(node, ast.Call):
            arg = node.args[0] if node.args else None
            first = arg.elts[0] if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts else arg
            literal = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            shell = next((kw.value for kw in node.keywords if kw.arg == 'shell'), None)
            calls.setdefault(str(node.lineno), []).append({
                'argument_form': 'sequence_expression' if isinstance(arg, (ast.List, ast.Tuple)) else 'literal_text' if literal is not None else 'dynamic_or_absent',
                'executable_path': 'absolute_literal' if literal and literal.startswith('/') else 'relative_literal' if literal else 'unknown',
                'shell_keyword': str(shell.value).lower() if isinstance(shell, ast.Constant) and type(shell.value) is bool else 'unspecified' if shell is None else 'dynamic',
            })
    return {'status': 'parsed', 'source_binding': binding, 'source_sha256': digest, 'parse_warning_count': len(parse_warnings),
            'statements': {str(k): sorted(v) for k, v in statements.items()}, 'calls': calls}


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


def investigate_candidate(candidate: Mapping, observation: Mapping, *, observed_commit: str,
                          expected_commit: str, expected_repository: str) -> dict:
    """Rule-specific, source-bound assistance; never assign a human disposition."""
    result = candidate_source_observation(candidate, observation, observed_commit=observed_commit,
        expected_commit=expected_commit, expected_repository=expected_repository)
    result.update(analysis_actor='deterministic_source_review_assistant', model_invocations=0,
                  bounded_rule_analysis_completed=False, rationale=[], counterevidence=[], unresolved_questions=[],
                  recommended_reviewer_action='request_missing_evidence')
    if result['status'] != 'structure_observed':
        result['unresolved_questions'] = [result['reason']]
        return result
    rule = candidate.get('rule_id') or candidate.get('rule')
    result['source_reference'] = {**result['source_binding'], 'line': candidate['line'],
                                'source_sha256': result['source_sha256']}
    result['bounded_rule_analysis_completed'] = True  # Only the explicitly bounded rule analysis below.
    result['investigation_scope'] = 'exact_line_rule_reasoning_without_runtime_or_dataflow'
    result['recommended_reviewer_action'] = 'retain_for_contextual_review'
    if rule == 'B101':
        result['rationale'] = ['An executable assert statement occurs at the retained line.',
                               'Python optimized execution can remove assertions; a required runtime check must not depend on this assertion.']
        result['counterevidence'] = ['An assertion can express a developer invariant without serving as a security check; its presence alone does not establish a vulnerability.']
        result['unresolved_questions'] = ['Does this assertion enforce authorization, input validation or another required runtime boundary?',
                                          'Can optimized Python execution occur in the supported deployment?',
                                          'Is an independent runtime check present on every reachable path?']
    elif rule in {'B404', 'B405'}:
        result['rationale'] = ['An import statement occurs at the retained line; the rule flags an API family requiring contextual review.']
        result['counterevidence'] = ['An import alone does not prove that an unsafe API is called or that untrusted input reaches it.']
        result['unresolved_questions'] = ['Which imported APIs are called on reachable production paths?',
                                          'Are untrusted inputs parsed or executed, and what validation or safe configuration applies?']
    else:
        calls = observation.get('calls', {}).get(str(candidate['line']), [])
        if len(calls) != 1:
            result.update(bounded_rule_analysis_completed=False, recommended_reviewer_action='request_missing_evidence')
            result['unresolved_questions'] = ['Multiple or missing call expressions prevent an unambiguous exact-line argument analysis.']
            return result
        result['argument_observations'] = calls[0]
        result['rationale'] = ['A call expression occurs at the retained line. Argument shape and shell keyword are syntactic observations, not resolved runtime behavior.']
        result['counterevidence'] = ['A shell-disabled or absolute-path call can still expose unsafe program arguments; neither observation clears this candidate.']
        result['unresolved_questions'] = ['Does this call resolve to the scanner-reported subprocess API, including aliases and shadowing?',
                                          'Can untrusted input control the executable, arguments, environment or working directory?',
                                          'Is executable lookup constrained to trusted locations?']
    return result
