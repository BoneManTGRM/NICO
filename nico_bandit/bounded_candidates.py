"""Two conservative review candidates on Bandit's existing AST, without evaluation.

No filesystem traversal, source reads, imports of assessed modules or dynamic
execution. Unsupported flow is not treated as proof of safety. See the scope
contract in docs/bounded-python-candidates.md.
"""
from __future__ import annotations

import ast
import logging

import bandit
from bandit.core import issue
from bandit.core import test_properties as test

MAX_NODES = 10_000
MAX_DEPTH = 64
_CACHE = '_nico_bounded_candidates_v1'
LOG = logging.getLogger(__name__)
_VERBS = {'get', 'options', 'head', 'post', 'put', 'patch', 'delete'}
_PROTECTED = {'requests', 'hashlib', 'getattr', '__builtins__'}
_DYNAMIC = {'exec', 'eval', 'globals', 'locals', 'vars', 'setattr', 'delattr', '__import__'}


def _literal(node):
    return isinstance(node, ast.Constant)


def _simple(node):
    return isinstance(node, (ast.Name, ast.Constant))


def _nodes(root):
    stack = [(root, 0)]
    result = []
    while stack:
        node, depth = stack.pop()
        if len(result) >= MAX_NODES or depth > MAX_DEPTH:
            return None
        result.append(node)
        for child in ast.iter_child_nodes(node):
            if len(result) + len(stack) >= MAX_NODES:
                return None
            stack.append((child, depth + 1))
    return result


def _module(root, nodes):
    """Require canonical imports and no module-level executable/rebinding flow."""
    imports = {}
    for statement in root.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                name = alias.asname or alias.name.split('.')[0]
                imports.setdefault(name, []).append((alias.name, statement.lineno))
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name in _PROTECTED or statement.decorator_list or getattr(statement, 'type_params', []):
                return None
            # Evaluated defaults/annotations could rebind modules at definition time.
            annotations = [a.annotation for a in (*statement.args.posonlyargs,
                           *statement.args.args, *statement.args.kwonlyargs)]
            annotations += [statement.returns]
            if statement.args.vararg:
                annotations.append(statement.args.vararg.annotation)
            if statement.args.kwarg:
                annotations.append(statement.args.kwarg.annotation)
            values = [*statement.args.defaults, *statement.args.kw_defaults, *annotations]
            if any(value is not None and not _literal(value) for value in values):
                return None
        elif not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                  and isinstance(statement.value.value, str)):
            return None
    for node in nodes:
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC:
            return None
        # Alias/member writes cannot be resolved locally; suppress the supplement
        # for the entire module, including writes hidden in sibling functions.
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            return None
    return imports


def _function(function):
    if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    args = function.args
    bound = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    bound.update(a.arg for a in (args.vararg, args.kwarg) if a is not None)
    if bound & _PROTECTED:
        return None
    constants = {}
    for statement in function.body[:-1]:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue
        if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name) and _literal(statement.value)):
            return None
        name = statement.targets[0].id
        if name in bound or name in _PROTECTED:
            return None  # No reassignments, including parameters, even to False.
        bound.add(name)
        constants[name] = statement.value.value
    final = function.body[-1] if function.body else None
    if not isinstance(final, ast.Return):
        return None
    return constants, final.value


def _canonical(imports, name, function):
    values = imports.get(name, [])
    return len(values) == 1 and values[0][0] == name and values[0][1] < function.lineno


def _tls(call, constants):
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name) and call.func.value.id == 'requests'
            and call.func.attr in _VERBS and all(_simple(a) for a in call.args)
            and all(k.arg is not None and _simple(k.value) for k in call.keywords)):
        return False
    verify = [k.value for k in call.keywords if k.arg == 'verify']
    return len(verify) == 1 and isinstance(verify[0], ast.Name) and constants.get(verify[0].id) is False


def _md5(value):
    call = value
    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr in {'digest', 'hexdigest'} and not call.args and not call.keywords):
        call = call.func.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Call):
        return None
    selector = call.func
    if not (isinstance(selector.func, ast.Name) and selector.func.id == 'getattr'
            and len(selector.args) == 2 and not selector.keywords
            and isinstance(selector.args[0], ast.Name) and selector.args[0].id == 'hashlib'
            and isinstance(selector.args[1], ast.Constant) and selector.args[1].value == 'md5'
            and all(_simple(a) for a in call.args)
            and all(k.arg is not None and _simple(k.value) for k in call.keywords)):
        return None
    security = [k.value for k in call.keywords if k.arg == 'usedforsecurity']
    if security and not (len(security) == 1 and isinstance(security[0], ast.Constant)
                         and security[0].value is True):
        return None
    return call


def _analyze(root):
    nodes = _nodes(root)
    if nodes is None:
        LOG.warning('NICO bounded Python candidates: AST resource limit; indirect candidate coverage unavailable')
        return {}
    imports = _module(root, nodes)
    if imports is None:
        return {}
    found = {}
    for function in root.body:
        supported = _function(function)
        if supported is None:
            continue
        constants, value = supported
        if _canonical(imports, 'requests', function) and _tls(value, constants):
            found[id(value)] = 'B951'
        if not imports.get('getattr') and _canonical(imports, 'hashlib', function):
            call = _md5(value)
            if call is not None:
                found[id(call)] = 'B952'
    return found


def _matches(context, rule):
    node = context.node
    root = node
    for _ in range(MAX_DEPTH + 1):
        parent = getattr(root, '_bandit_parent', None)
        if parent is None:
            break
        root = parent
    if not isinstance(root, ast.Module):
        LOG.warning('NICO bounded Python candidates: parent depth limit; indirect candidate coverage unavailable')
        return False
    if not hasattr(root, _CACHE):
        setattr(root, _CACHE, _analyze(root))
    return getattr(root, _CACHE).get(id(node)) == rule


@test.checks('Call')
@test.test_id('B951')
def nico_requests_bound_false(context):
    call = context.node
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in _VERBS
            and any(k.arg == 'verify' and isinstance(k.value, ast.Name) for k in call.keywords)):
        return None
    if _matches(context, 'B951'):
        return bandit.Issue(
            severity=bandit.MEDIUM, confidence=bandit.MEDIUM,
            cwe=issue.Cwe.IMPROPER_CERT_VALIDATION,
            text='Review candidate: requests TLS verification receives a sole local False assignment. '
                 'Human review required; not an approved disposition.',
            lineno=context.node.lineno,
        )


@test.checks('Call')
@test.test_id('B952')
def nico_hashlib_getattr_md5(context):
    call = context.node
    if not (isinstance(call.func, ast.Call) and isinstance(call.func.func, ast.Name)
            and call.func.func.id == 'getattr'):
        return None
    if _matches(context, 'B952'):
        return bandit.Issue(
            severity=bandit.MEDIUM, confidence=bandit.MEDIUM,
            cwe=issue.Cwe.BROKEN_CRYPTO,
            text='Review candidate: constant getattr selects hashlib MD5. MD5 use is not universally '
                 'a vulnerability; security-sensitive use and exploitability require human review.',
            lineno=context.node.lineno,
        )
