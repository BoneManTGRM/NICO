from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.complexity-source-context.v1"
_MAX_LINES = 9
_SECRET = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)(\s*[:=]\s*)['\"]?[^\s'\"]{8,}"
)


def _redact(line: str) -> str:
    return _SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", line)


def _excerpt(text: str, start_line: int, end_line: int | None) -> tuple[str, int]:
    lines = text.splitlines()
    if not (1 <= start_line <= len(lines)):
        return "", start_line
    bounded_end = min(
        len(lines),
        max(start_line, min(int(end_line or start_line + _MAX_LINES - 1), start_line + _MAX_LINES - 1)),
    )
    selected = [f"{line_number}: {_redact(lines[line_number - 1].rstrip())}" for line_number in range(start_line, bounded_end + 1)]
    return "\n".join(selected), bounded_end


def attach_complexity_source_context(
    evidence: Mapping[str, Any],
    files: Mapping[str, str],
) -> dict[str, Any]:
    """Attach a bounded, redacted excerpt to every retained exact-source hotspot."""

    result = deepcopy(dict(evidence))
    hotspots: list[dict[str, Any]] = []
    retained = 0
    for raw in result.get("hotspots") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        path = str(item.get("path") or "")
        line = int(item.get("line") or 0)
        text = files.get(path)
        if isinstance(text, str) and line > 0:
            excerpt, excerpt_end = _excerpt(text, line, item.get("end_line"))
            if excerpt:
                item.update(
                    {
                        "source_excerpt": excerpt,
                        "source_excerpt_start_line": line,
                        "source_excerpt_end_line": excerpt_end,
                        "source_context_retained": True,
                        "source_context_redacted": True,
                    }
                )
                retained += 1
        hotspots.append(item)
    result["hotspots"] = hotspots
    result["source_context_version"] = VERSION
    result["source_context_hotspot_count"] = retained
    result["source_context_coverage"] = round(retained / len(hotspots), 4) if hotspots else 1.0
    result["retention_note"] = (
        "Numeric complexity summaries and exact source anchors are retained with at most nine redacted source lines per reported hotspot; full source files are not embedded in the evidence object."
    )
    return result


__all__ = ["VERSION", "attach_complexity_source_context"]
