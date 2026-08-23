#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

VERSION = "nico.provider_neutral_repository_locator_contract.v1"
LEGACY_ENGLISH_REPOSITORY_LABEL = "Repository owner/name or GitHub URL"
ENGLISH_REPOSITORY_LABEL = "Repository URL or identifier"
SPANISH_REPOSITORY_LABEL = "URL o identificador del repositorio"
_MARKER = "__nico_provider_neutral_repository_locator_v1__"


def install_provider_neutral_repository_locator(single_dispatch: Any) -> None:
    """Keep legacy proof entrypoints bound to the current provider-neutral UI.

    The production form intentionally stopped presenting a GitHub-only repository
    label when hosted-provider parity shipped. Older recovery proof code still
    asks its wrapped page for that historical label. Patch only the internal
    proof-page adapter so the proof continues to exercise the real current field;
    never add the obsolete GitHub-only label back to the application.
    """

    page_type = single_dispatch._SingleDispatchPage
    current = getattr(page_type, "get_by_label", None)
    if getattr(current, _MARKER, False):
        return

    def get_by_label(self: Any, label: Any, *args: Any, **kwargs: Any) -> Any:
        target = (
            ENGLISH_REPOSITORY_LABEL
            if str(label) == LEGACY_ENGLISH_REPOSITORY_LABEL
            else label
        )
        if current is not None:
            return current(self, target, *args, **kwargs)
        return self._page.get_by_label(target, *args, **kwargs)

    setattr(get_by_label, _MARKER, True)
    setattr(get_by_label, "_nico_previous", current)
    setattr(page_type, "get_by_label", get_by_label)
