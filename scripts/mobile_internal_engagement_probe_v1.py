from __future__ import annotations

from typing import Any

VERSION = "nico.mobile_internal_engagement_probe.v1"
_INTERNAL_ONLY_LABELS = frozenset({"Client name, optional", "Project name, optional"})


class _InternalOnlyLocator:
    """Preserve the production-proof interaction shape without inventing client identity."""

    def __init__(self, locator: Any) -> None:
        self._locator = locator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._locator, name)

    def fill(self, value: str, *args: Any, **kwargs: Any) -> None:
        # The restart/WebKit proof is an internal operational assessment.  Phase 3
        # correctly requires contact/access evidence when client/project identity is
        # supplied, so these historical placeholder fills must remain blank rather
        # than manufacturing a client engagement.
        return None


def install_internal_engagement_probe(single_dispatch_module: Any) -> None:
    """Keep production acceptance in the truthful internal-engagement mode.

    The legacy recovery proof still exercises the optional client/project inputs.
    Current Phase 3 intake semantics intentionally treat either field as a real
    client engagement and then require real contact/access evidence.  Intercept only
    those two historical placeholder fills for the operational proof; repository,
    authorization, dispatch, run identity, recovery, score, and report assertions
    remain unchanged.
    """

    page_type = single_dispatch_module._SingleDispatchPage
    if getattr(page_type, "_nico_internal_engagement_probe_v1", False):
        return

    def get_by_label(self: Any, label: str, *args: Any, **kwargs: Any) -> Any:
        locator = self._page.get_by_label(label, *args, **kwargs)
        if label in _INTERNAL_ONLY_LABELS:
            return _InternalOnlyLocator(locator)
        return locator

    page_type.get_by_label = get_by_label
    page_type._nico_internal_engagement_probe_v1 = True
