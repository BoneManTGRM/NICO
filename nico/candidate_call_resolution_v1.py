"""Conservative lexical import binding, not runtime dispatch or safety proof."""
import ast
import re
from collections import Counter
from collections.abc import Mapping

VERSION = 'nico.candidate-call-resolution.v1'
APIS = frozenset({'run', 'Popen', 'call', 'check_call', 'check_output'})
QUALIFIED_APIS = frozenset('subprocess.' + name for name in APIS)
RULES = frozenset({'B603', 'B607'})
SCOPE_KEYS = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')


def resolve_calls(tree):
    """Resolve only unconditional module imports with no observed rebinding.

    Shadowing anywhere in the file conservatively invalidates that name, even
    in unrelated scopes. Dynamic namespace operations invalidate all bindings.
    External monkeypatching and import-hook behavior are outside this proof.
    No arbitrary source identifiers or argument values leave this function.
    """
    nodes = list(ast.walk(tree))
    imports, bound, unsafe = {}, Counter(), set()
    dynamic = False
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                bound[name] += 1
                if alias.name == '*':
                    dynamic = True
                if node not in tree.body:
                    continue
                if isinstance(node, ast.Import) and alias.name == 'subprocess':
                    imports[name] = ('subprocess', node.lineno)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == 'subprocess' and alias.name in APIS:
                    imports[name] = ('subprocess.' + alias.name, node.lineno)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            unsafe.add(node.id)
        elif isinstance(node, ast.arg):
            unsafe.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            unsafe.add(node.name)
            unsafe.update(item.name for item in getattr(node, 'type_params', []))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            unsafe.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            unsafe.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            unsafe.add(node.rest)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            unsafe.update(node.names)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                unsafe.add(root.id)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in {'exec', 'eval', 'globals', 'locals', 'vars', 'setattr', 'delattr', '__import__'}:
                dynamic = True
        if isinstance(node, ast.Attribute) and node.attr == '__dict__':
            dynamic = True

    result = {}
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        value = {'status': 'unresolved', 'reason': 'dynamic_or_unbound_call'}
        root = node.func if isinstance(node.func, ast.Name) else node.func.value if isinstance(node.func, ast.Attribute) else None
        if isinstance(root, ast.Name) and root.id in imports:
            api, line = imports[root.id]
            if isinstance(node.func, ast.Attribute):
                api = api + '.' + node.func.attr if api == 'subprocess' else ''
            if dynamic:
                value['reason'] = 'dynamic_namespace'
            elif root.id in unsafe or bound[root.id] != 1:
                value['reason'] = 'shadowed_or_rebound_import'
            elif line >= node.lineno:
                value['reason'] = 'import_order_unproven'
            elif api in QUALIFIED_APIS:
                value = {'status': 'resolved', 'reason': 'unshadowed_module_import',
                         'api': api, 'import_line': line}
        result[id(node)] = value
    return result


def _candidate_call_fact(candidate, capture, scope):
    """Bind a persisted parser observation to the exact scanner claim and tenant.

    Capture is supplied by the trusted scan worker, never by candidate prose.
    Legacy decoded-text observations and older parser output cannot gain credit.
    """
    from nico.candidate_source_observations_v1 import candidate_source_observation, candidate_source_path

    eligible = (candidate.get('category') == 'static'
                and (candidate.get('scanner') or candidate.get('tool')) == 'bandit'
                and (candidate.get('rule_id') or candidate.get('rule')) in RULES)
    if not eligible:
        return None
    result = {'version': VERSION, 'attempted': False, 'status': 'unresolved',
              'reason': 'bound_capture_unavailable'}
    if candidate.get('candidate_evidence_context_status') == 'ambiguous':
        return {**result, 'reason': 'ambiguous_candidate_context'}
    if (not isinstance(scope, Mapping) or not all(isinstance(scope.get(k), str) and scope[k] for k in SCOPE_KEYS)
            or not isinstance(capture, Mapping)
            or capture.get('artifact_schema') != 'nico.persisted-candidate-investigation.v1'
            or capture.get('scope') != {k: scope[k] for k in SCOPE_KEYS}):
        return result
    observations = capture.get('observations')
    path = candidate_source_path(candidate.get('source_path') or candidate.get('path'))
    observation = observations.get(path) if isinstance(observations, Mapping) and path else None
    if not isinstance(observation, Mapping):
        return result
    structural = candidate_source_observation(candidate, observation,
        observed_commit=scope['commit_sha'], expected_commit=scope['commit_sha'], expected_repository=scope['repository'])
    if structural['status'] != 'structure_observed':
        return {**result, 'reason': structural['reason']}
    binding = observation.get('source_binding', {})
    if (observation.get('call_resolution_version') != VERSION or observation.get('complete_source_blob') is not True
            or observation.get('parse_warning_count') != 0
            or not re.fullmatch('[0-9a-f]{40}', str(binding.get('blob_oid', '')))
            or not re.fullmatch('[0-9a-f]{64}', str(observation.get('source_sha256', '')))):
        return {**result, 'reason': 'complete_parser_proof_unavailable'}
    result['attempted'] = True
    calls = observation.get('calls', {}).get(str(candidate['line']), [])
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], Mapping):
        return {**result, 'reason': 'ambiguous_call_expression'}
    resolution = calls[0].get('api_binding')
    if not isinstance(resolution, Mapping) or resolution.get('status') != 'resolved':
        reason = resolution.get('reason') if isinstance(resolution, Mapping) else None
        return {**result, 'reason': reason if reason in {'dynamic_namespace', 'shadowed_or_rebound_import', 'import_order_unproven', 'dynamic_or_unbound_call'} else 'call_binding_unavailable'}
    api, line = resolution.get('api'), resolution.get('import_line')
    if api not in QUALIFIED_APIS or type(line) is not int or not 0 < line < candidate['line']:
        return {**result, 'reason': 'call_binding_unavailable'}
    return {**result, 'status': 'resolved', 'reason': 'unshadowed_module_import',
            'api': api, 'import_line': line, 'line': candidate['line'],
            'scope': {k: scope[k] for k in SCOPE_KEYS}, 'path': path,
            'source_sha256': observation['source_sha256'], 'blob_oid': binding['blob_oid'],
            'proof_scope': 'static_import_binding_and_call_syntax_only',
            'runtime_validation_performed': False}


def candidate_call_fact(candidate, capture, scope):
    try:
        return _candidate_call_fact(candidate, capture, scope)
    except (ValueError, TypeError, AttributeError, RecursionError):
        return {'version': VERSION, 'attempted': False, 'status': 'unresolved',
                'reason': 'retained_observation_invalid'}
