from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|jwt|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{16,})"),
]


def mask_secret_value(value: str) -> str:
    if not value:
        return "***"
    if len(value) <= 8:
        return "***"
    return value[:4] + "…" + value[-4:]


def mask_text(text: str) -> str:
    masked = text
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub(
            lambda match: (
                match.group(1) + '="' + mask_secret_value(match.group(2)) + '"'
                if match.lastindex and match.lastindex >= 2
                else mask_secret_value(match.group(0))
            ),
            masked,
        )
    return masked


def has_secret_like_value(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in SECRET_PATTERNS)
