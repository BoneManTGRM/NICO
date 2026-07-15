from __future__ import annotations

from typing import Any

_INSTALL_MARKER = "_nico_complexity_score_integrity_reentry_v1"


def install_complexity_score_integrity_reentry_compat() -> dict[str, Any]:
    """Ensure repeated integrity-patch installation also restores compatibility.

    NICO's package installers are intentionally idempotent and may be invoked again by
    startup validation or tests. Reinstalling the core integrity patch must not remove
    the legacy non-scoring attachment wrapper installed immediately afterward.
    """

    from nico import complexity_score_integrity_patch as integrity
    from nico.complexity_score_integrity_compat import install_complexity_score_integrity_compat

    current = integrity.install_complexity_score_integrity_patch
    if getattr(current, _INSTALL_MARKER, False):
        return {"status": "already_installed", "compatibility_restored_on_reentry": True}

    original = current

    def install_with_compatibility() -> dict[str, Any]:
        result = dict(original())
        result["attachment_compatibility"] = install_complexity_score_integrity_compat()
        result["compatibility_restored_on_reentry"] = True
        return result

    setattr(install_with_compatibility, _INSTALL_MARKER, True)
    setattr(install_with_compatibility, "_nico_previous", original)
    integrity.install_complexity_score_integrity_patch = install_with_compatibility
    return {"status": "installed", "compatibility_restored_on_reentry": True}


__all__ = ["install_complexity_score_integrity_reentry_compat"]
