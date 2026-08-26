from __future__ import annotations

import io
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

from nico import comprehensive_semantic_navigation_v2 as v2

VERSION = "nico.comprehensive_semantic_navigation.v3"
_MARKER = "__nico_comprehensive_semantic_navigation_v3__"


def _render_semantic_navigation(
    pdf_bytes: bytes,
    *,
    legacy: Callable[[bytes], bytes],
) -> bytes:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("final Comprehensive PDF contains no pages")

    entries, spanish = v2.semantic_entries(reader)
    if not entries:
        # Use the exact pre-v3 delegate captured at installation time. This is stable
        # even when the production bootstrap is imported repeatedly by tests or worker
        # startup because it never resolves the mutable public alias again.
        return legacy(pdf_bytes)

    total = len(reader.pages) + 1
    toc = PdfReader(
        io.BytesIO(v2._toc_page(entries, total, spanish=spanish))
    ).pages[0]
    writer = PdfWriter()
    source_pages: list[tuple[Any, bool]] = [
        (reader.pages[0], True),
        (toc, False),
    ]
    source_pages.extend((page, True) for page in reader.pages[1:])

    for index, (source, rewrite_labels) in enumerate(source_pages, start=1):
        writer.add_page(source)
        page = writer.pages[-1]
        if rewrite_labels:
            navigation._rewrite_local_page_labels(page, writer)
        overlay = PdfReader(
            io.BytesIO(v2._page_overlay(index, total, spanish=spanish))
        ).pages[0]
        page.merge_page(overlay, over=True)

    try:
        writer.add_outline_item(
            "Tabla de contenido" if spanish else "Table of Contents",
            1,
        )
    except Exception:
        pass
    for title, page_number in entries:
        try:
            writer.add_outline_item(title, page_number - 1)
        except Exception:
            pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_comprehensive_semantic_navigation_v3() -> dict[str, Any]:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._renumber_and_outline
    if getattr(current, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "non_recursive_fallback": True,
            "multiple_sections_per_page_supported": True,
            "semantic_toc_complete": True,
            "bilingual_toc_and_page_labels": True,
            "canonical_truth_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    # If v2 was already installed by an earlier import in this process, unwrap its
    # wrapper chain once to the stable pre-v2 navigation delegate. Do not call through
    # a semantic wrapper as a fallback, because repeated installation previously caused
    # an infinite semantic -> fallback -> semantic recursion on PDFs with unknown titles.
    legacy = current
    seen: set[int] = set()
    while callable(legacy) and id(legacy) not in seen:
        seen.add(id(legacy))
        if not getattr(legacy, v2._MARKER, False):
            break
        previous = getattr(legacy, "_nico_previous", None)
        if not callable(previous):
            break
        legacy = previous
    if not callable(legacy):
        raise RuntimeError("semantic navigation v3 has no stable legacy delegate")

    @wraps(current)
    def semantic_navigation(pdf_bytes: bytes) -> bytes:
        return _render_semantic_navigation(pdf_bytes, legacy=legacy)

    setattr(semantic_navigation, _MARKER, True)
    setattr(semantic_navigation, "_nico_previous", current)
    setattr(semantic_navigation, "_nico_legacy_fallback", legacy)
    navigation._renumber_and_outline = semantic_navigation
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "non_recursive_fallback": True,
        "multiple_sections_per_page_supported": True,
        "semantic_toc_complete": True,
        "bilingual_toc_and_page_labels": True,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_semantic_navigation_v3",
]
