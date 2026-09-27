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

    copies: dict[int, Any] = {}

    def clone(item: Any, depth: int = 0) -> Any:
        kind = type(item)
        if kind is str or kind is int or kind is float or kind is bool or kind is _NONE_TYPE:
            return item
        if kind is not dict and kind is not list:
            raise _UseLegacyCopy
        identity = id(item)
        if identity in copies:
            return copies[identity]
        if depth >= _FAST_DEPTH_LIMIT:
            raise _UseLegacyCopy
        if kind is dict:
            result: Any = {}
            copies[identity] = result
            for key, child in item.items():
                if type(key) is not str:
                    raise _UseLegacyCopy
                result[key] = clone(child, depth + 1)
        else:
            result = []
            copies[identity] = result
            result.extend(clone(child, depth + 1) for child in item)
        return result

    try:
        return clone(value)
    except (_UseLegacyCopy, RecursionError):
        pass
    # Leave the exception scope before legacy copying so its traceback and the
    # speculative graph do not remain deliberately retained during the fallback.
    copies.clear()
    return _legacy_deepcopy(value)


__all__ = ["deepcopy"]
