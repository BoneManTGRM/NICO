from __future__ import annotations

import contextvars
from functools import wraps
from typing import Any

VERSION = "nico.comprehensive_report_flatten_bound.v1"
_INSTALL_MARKER = "_nico_comprehensive_report_flatten_bound_v1"
MAX_FLATTEN_VISITS = 6_000

_BUDGET: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "nico_comprehensive_flatten_budget",
    default=None,
)


def install_bounded_report_flatten() -> bool:
    """Bound recursive report detail traversal without changing rendered content rules.

    The native report flattener stops after a fixed number of emitted lines, but a deeply
    nested list can contain thousands of nodes that emit no scalar line before the depth
    limit. This replacement shares one visit budget across recursion so retained scanner
    and repository payloads cannot hold final report generation for minutes.
    """

    from nico import comprehensive_report_package as report_module

    current = report_module._flatten
    if getattr(current, _INSTALL_MARKER, False):
        return False

    @wraps(current)
    def bounded(
        value: Any,
        *,
        prefix: str = "",
        depth: int = 0,
        maximum: int = 120,
    ) -> list[str]:
        root = _BUDGET.get() is None
        token = None
        if root:
            token = _BUDGET.set([0])
        visits = _BUDGET.get()
        assert visits is not None
        try:
            visits[0] += 1
            if depth > 5 or visits[0] > MAX_FLATTEN_VISITS:
                return []
            output: list[str] = []
            if isinstance(value, dict):
                for key, item in value.items():
                    visits[0] += 1
                    if visits[0] > MAX_FLATTEN_VISITS:
                        break
                    if str(key) in report_module._IGNORED_DETAIL_KEYS:
                        continue
                    label = f"{prefix}.{key}" if prefix else str(key)
                    if isinstance(item, (dict, list, tuple)):
                        output.extend(
                            bounded(
                                item,
                                prefix=label,
                                depth=depth + 1,
                                maximum=maximum,
                            )
                        )
                    elif item not in (None, ""):
                        output.append(
                            f"{label}: {report_module._text(item, 700)}"
                        )
                    if len(output) >= maximum:
                        break
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    visits[0] += 1
                    if visits[0] > MAX_FLATTEN_VISITS:
                        break
                    label = f"{prefix}[{index}]" if prefix else str(index + 1)
                    if isinstance(item, (dict, list, tuple)):
                        output.extend(
                            bounded(
                                item,
                                prefix=label,
                                depth=depth + 1,
                                maximum=maximum,
                            )
                        )
                    elif item not in (None, ""):
                        output.append(
                            f"{label}: {report_module._text(item, 700)}"
                        )
                    if len(output) >= maximum:
                        break
            elif value not in (None, ""):
                output.append(
                    f"{prefix}: {report_module._text(value, 700)}"
                    if prefix
                    else report_module._text(value, 700)
                )
            return output[:maximum]
        finally:
            if root and token is not None:
                _BUDGET.reset(token)

    setattr(bounded, _INSTALL_MARKER, True)
    setattr(bounded, "_nico_original_flatten", current)
    report_module._flatten = bounded
    return True


__all__ = [
    "MAX_FLATTEN_VISITS",
    "VERSION",
    "install_bounded_report_flatten",
]
