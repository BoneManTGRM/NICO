"""Reuse unchanged PDF text within an explicitly scoped report attempt.

Importing this module changes no parser or validator. Outside an explicit scope,
every call performs the original default pypdf extraction. Cached values are
text only: callers must still perform all identity, content and approval checks.
"""
from __future__ import annotations

import io
import sys
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from pypdf import PdfReader

from nico.report_delivery_timing_v1 import report_delivery_phase


_MAX_ENTRIES = 4
# Reserve four MiB of the existing sixteen-MiB report cache allowance for
# immutable retained PDFs. Together with one active text attempt, the cache
# allowance is unchanged; additional text attempts have the smaller ceiling.
_MAX_RETAINED_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class _TextEntry:
    pages: tuple[str, ...]
    retained_bytes: int


class _AttemptCache:
    def __init__(self) -> None:
        self.owner_thread = threading.get_ident()
        self.entries: OrderedDict[bytes, _TextEntry] = OrderedDict()
        self.retained_bytes = 0
        self._lock = threading.RLock()
        self._active = True

    def get(self, pdf: bytes) -> tuple[str, ...] | None:
        with self._lock:
            if not self._active:
                return None
            entry = self.entries.get(pdf)
            if entry is None:
                return None
            self.entries.move_to_end(pdf)
            return entry.pages

    def put(self, pdf: bytes, pages: tuple[str, ...]) -> None:
        # Count the retained Python bytes object, tuple, and every page string.
        # Repeated string identities count repeatedly, a conservative upper bound.
        # The bounded four-entry index and fixed entry metadata are not PDF text.
        if any(type(page) is not str for page in pages):
            return
        retained = sys.getsizeof(pdf) + sys.getsizeof(pages)
        retained += sum(sys.getsizeof(page) for page in pages)
        if retained > _MAX_RETAINED_BYTES:
            return
        with self._lock:
            if not self._active:
                return
            previous = self.entries.pop(pdf, None)
            if previous is not None:
                self.retained_bytes -= previous.retained_bytes
            while self.entries and (
                len(self.entries) >= _MAX_ENTRIES
                or self.retained_bytes + retained > _MAX_RETAINED_BYTES
            ):
                _, evicted = self.entries.popitem(last=False)
                self.retained_bytes -= evicted.retained_bytes
            self.entries[pdf] = _TextEntry(pages, retained)
            self.retained_bytes += retained

    def clear(self) -> None:
        with self._lock:
            self._active = False
            self.entries.clear()
            self.retained_bytes = 0


_ATTEMPT_CACHE: ContextVar[_AttemptCache | None] = ContextVar(
    "nico_report_pdf_text_attempt_cache", default=None
)


@contextmanager
def pdf_text_cache_scope() -> Iterator[None]:
    """Create an isolated attempt cache, restoring any outer scope on exit.

    Child tasks inherit their attempt's context. A nested scope starts fresh.
    Threads never reuse another thread's cache, even with a copied Context.
    Cache entries are cleared on every exit, including exceptions. A copied
    context that outlives the scope cannot repopulate its closed attempt cache.
    """
    cache = _AttemptCache()
    token = _ATTEMPT_CACHE.set(cache)
    try:
        yield
    finally:
        _ATTEMPT_CACHE.reset(token)
        cache.clear()


@report_delivery_phase("pdf_text_parse")
def _parse_pdf_page_texts(pdf: bytes) -> tuple[str, ...]:
    reader = PdfReader(io.BytesIO(pdf))
    return tuple(page.extract_text() or "" for page in reader.pages)


@report_delivery_phase("pdf_text_lookup")
def extract_pdf_page_texts(pdf: bytes) -> tuple[str, ...]:
    """Return complete, unnormalized default extraction, including blank pages.

    Exact immutable bytes are the cache key; mutable buffers and subclasses use
    the uncached path. Oversized inputs/results still extract in full. Parser or
    extraction failures propagate unchanged and never become cache entries.
    """
    cache = _ATTEMPT_CACHE.get()
    eligible = (
        cache is not None
        and cache.owner_thread == threading.get_ident()
        and type(pdf) is bytes
    )
    if eligible:
        cached = cache.get(pdf)
        if cached is not None:
            return cached
    pages = _parse_pdf_page_texts(pdf)
    if eligible:
        cache.put(pdf, pages)
    return pages


__all__ = ["extract_pdf_page_texts", "pdf_text_cache_scope"]
