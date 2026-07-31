from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico import scanner_determinism_v1 as determinism

VERSION = "nico.scanner-determinism-reentry.v2"
_MARKER = "__nico_scanner_determinism_reentry_v2__"
_ORIGINAL_ATTR = "_nico_scanner_determinism_original_installer_v2"


def install_scanner_determinism_reentry() -> dict[str, Any]:
    """Make the deterministic scanner installer safely re-entrant.

    NICO retains compatibility installers that can replace scanner functions after
    the original deterministic installer has run. The legacy installer correctly
    avoided duplicate wrappers, but its process-global early return prevented it
    from repairing those later replacements. This boundary preserves idempotent
    wrappers while allowing every explicit installer call to reassert exact-SHA
    checkout, immutable scanner inputs, canonical finding order, and fingerprints.
    """

    current: Callable[[], dict[str, Any]] = determinism.install_scanner_determinism
    if not getattr(current, _MARKER, False):
        original = getattr(determinism, _ORIGINAL_ATTR, current)

        @wraps(original)
        def reentrant_install() -> dict[str, Any]:
            # The original installer already checks wrapper markers before adding
            # them. Clearing only its early-return flag therefore repairs replaced
            # bindings without stacking duplicate deterministic wrappers.
            determinism._INSTALLED = False
            return dict(original())

        setattr(reentrant_install, _MARKER, True)
        setattr(reentrant_install, "_nico_previous", original)
        setattr(determinism, _ORIGINAL_ATTR, original)
        determinism.install_scanner_determinism = reentrant_install

    status = dict(determinism.install_scanner_determinism())
    from nico import scanner_tool_runners as runners
    from nico import snapshot_scanner_worker as snapshot

    clone_bound = snapshot.clone_repository_at_snapshot is determinism.clone_repository_at_snapshot
    runner_bound = bool(
        getattr(runners.run_scanner_tool, "__nico_deterministic_runner__", False)
    )
    specs = {spec.name: spec for spec in runners.TOOL_SPECS}
    head_bound = bool(
        specs.get("gitleaks")
        and specs["gitleaks"].command[-1] == "HEAD"
        and specs.get("trufflehog")
        and specs["trufflehog"].command[-1] == "HEAD"
    )
    return {
        **status,
        "status": "installed" if clone_bound and runner_bound and head_bound else "blocked",
        "reentry_version": VERSION,
        "reentrant_installer_bound": bool(
            getattr(determinism.install_scanner_determinism, _MARKER, False)
        ),
        "exact_commit_ancestry_clone_bound": clone_bound,
        "deterministic_runner_outermost": runner_bound,
        "history_scanners_bound_to_head": head_bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_scanner_determinism_reentry"]
