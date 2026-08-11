#!/usr/bin/env python3
from __future__ import annotations

import re
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VERSION = "nico.mobile_exact_sha_navigation.v1"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_MARKER = "_nico_exact_sha_navigation_v1"


def bind_expected_sha(url: str, expected_sha: str) -> str:
    """Bind only NICO assessment-page navigation to one immutable release SHA."""

    expected = str(expected_sha or "").strip().lower()
    if not _SHA_RE.fullmatch(expected):
        raise ValueError("expected_commit_sha_must_be_40_hex")
    parsed = urlsplit(str(url))
    if parsed.path.rstrip("/") not in {"/assessment", "/es/assessment"}:
        return str(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing = str(query.get("expected_commit_sha") or "").strip().lower()
    if existing and existing != expected:
        raise ValueError("expected_commit_sha_navigation_conflict")
    query["expected_commit_sha"] = expected
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def install_exact_sha_navigation(single_dispatch: ModuleType, expected_sha: str) -> dict[str, Any]:
    """Wrap the production-proof page navigation without changing application code."""

    expected = str(expected_sha or "").strip().lower()
    if not _SHA_RE.fullmatch(expected):
        raise ValueError("expected_commit_sha_must_be_40_hex")
    page_type = getattr(single_dispatch, "_SingleDispatchPage")
    current = page_type.goto
    previous = getattr(current, "_nico_previous", current)

    def goto(self: Any, *args: Any, **kwargs: Any) -> Any:
        positional = list(args)
        if positional:
            positional[0] = bind_expected_sha(str(positional[0]), expected)
        elif "url" in kwargs:
            kwargs = {**kwargs, "url": bind_expected_sha(str(kwargs["url"]), expected)}
        return previous(self, *positional, **kwargs)

    setattr(goto, _MARKER, True)
    setattr(goto, "_nico_previous", previous)
    setattr(goto, "_nico_expected_sha", expected)
    page_type.goto = goto
    return {
        "status": "installed",
        "version": VERSION,
        "expected_commit_sha": expected,
        "assessment_navigation_bound": True,
        "non_assessment_navigation_unchanged": True,
    }


__all__ = ["VERSION", "bind_expected_sha", "install_exact_sha_navigation"]
