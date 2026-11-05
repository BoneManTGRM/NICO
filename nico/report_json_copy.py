"""Copy plain report JSON graphs without repeated generic type dispatch.

This helper has no installation or global patching side effects. Callers opt in
explicitly. Unknown Python types and caller-supplied memos use standard deepcopy.
"""
from __future__ import annotations

from copy import deepcopy as _legacy_deepcopy
from typing import Any


_MEMO_UNSET = object()
_NONE_TYPE = type(None)
_FAST_DEPTH_LIMIT = 64


class _UseLegacyCopy(Exception):
    pass


def deepcopy(value: Any, memo: Any = _MEMO_UNSET) -> Any:
    """Preserve JSON values, order and alias graphs, with an opaque-type fallback.

    Only exact builtin dict/list containers, string keys and immutable JSON
    scalars enter the fast path. No custom methods run during its speculative
    traversal. If any unsupported value is reached, discard that traversal and
    copy the original graph through the standard implementation exactly once.
    Deep graphs also delegate to preserve standard recursion behavior.
    """
    if memo is not _MEMO_UNSET:
        return _legacy_deepcopy(value, memo)

    kind = type(value)
    if kind is str or kind is int or kind is float or kind is bool or kind is _NONE_TYPE:
        return value
    return copy_with_tree_ownership(value)[0]


def copy_with_tree_ownership(value: Any) -> tuple[Any, bool]:
    """Copy and certify only plain JSON trees with no shared mutable containers.

    A true flag lets an owner reuse subtrees of this private copy. Aliases,
    cycles, custom types and depth fallback never receive that guarantee.
    """
    kind = type(value)
    if kind is str or kind is int or kind is float or kind is bool or kind is _NONE_TYPE:
        return value, True

    copies: dict[int, Any] = {}
    unaliased_tree = True

    def clone(item: Any, depth: int = 0) -> Any:
        nonlocal unaliased_tree
        kind = type(item)
        if kind is not dict and kind is not list:
            raise _UseLegacyCopy
        identity = id(item)
        if identity in copies:
            unaliased_tree = False
            return copies[identity]
        if depth >= _FAST_DEPTH_LIMIT:
            raise _UseLegacyCopy
        # Exact builtin shallow copies retain immutable scalar identities in C.
        # Memoize before replacing containers so aliases and cycles stay intact.
        result = item.copy()
        copies[identity] = result
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise _UseLegacyCopy
                child_kind = type(child)
                if (child_kind is str or child_kind is int or child_kind is float
                        or child_kind is bool or child_kind is _NONE_TYPE):
                    continue
                result[key] = clone(child, depth + 1)
        else:
            for index, child in enumerate(item):
                child_kind = type(child)
                if (child_kind is str or child_kind is int or child_kind is float
                        or child_kind is bool or child_kind is _NONE_TYPE):
                    continue
                result[index] = clone(child, depth + 1)
        return result

    try:
        result = clone(value)
        return result, unaliased_tree
    except (_UseLegacyCopy, RecursionError):
        pass
    # Leave the exception scope before legacy copying so its traceback and the
    # speculative graph do not remain deliberately retained during the fallback.
    copies.clear()
    return _legacy_deepcopy(value), False


__all__ = ["deepcopy", "copy_with_tree_ownership"]
