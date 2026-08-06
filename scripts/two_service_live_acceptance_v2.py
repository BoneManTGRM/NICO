#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


# Source-level workflow contracts retained by this compatibility loader:
# acceptance.status_reconnect = status_reconnect
# acceptance.run_service = run_service
# return f"{parsed.scheme}://{parsed.netloc}{path}"
# APIRequestContext: Invalid URL
# COMPREHENSIVE_HARD_EXTENSION_SECONDS
# COMPREHENSIVE_STALE_SECONDS
# backend_status_history
# runtime-diagnostic.json
_MODULE_DIR = Path(__file__).resolve().parent
_LEGACY_MODULE_NAME = "_nico_two_service_live_acceptance_v2_legacy"
_LEGACY_PATH = _MODULE_DIR / "two_service_live_acceptance_v2_legacy.py"
_BOUNDED_MODULE_NAME = "_nico_bounded_terminal_reconnect_v1"
_BOUNDED_PATH = _MODULE_DIR / "bounded_terminal_reconnect_v1.py"


def _load_sibling(name: str, path: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if isinstance(existing, ModuleType):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Required compatibility module could not be loaded: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _load_legacy() -> ModuleType:
    return _load_sibling(_LEGACY_MODULE_NAME, _LEGACY_PATH)


_bounded = _load_sibling(_BOUNDED_MODULE_NAME, _BOUNDED_PATH)
install_bounded_terminal_reconnect = _bounded.install
_legacy = _load_legacy()
BOUNDED_TERMINAL_RECONNECT = install_bounded_terminal_reconnect(
    _legacy,
    _legacy.acceptance,
)

for _name in dir(_legacy):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_legacy, _name)

# Preserve an explicit loader identity while exposing the established module API.
LOADER_VERSION = "nico.two_service_live_acceptance_v2.loader.v2"


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
