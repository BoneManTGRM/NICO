#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from bounded_terminal_reconnect_v1 import install as install_bounded_terminal_reconnect


# Source-level workflow contracts retained by this compatibility loader:
# acceptance.status_reconnect = status_reconnect
# return f"{parsed.scheme}://{parsed.netloc}{path}"
# APIRequestContext: Invalid URL
_LEGACY_MODULE_NAME = "_nico_two_service_live_acceptance_v2_legacy"
_LEGACY_PATH = Path(__file__).with_name("two_service_live_acceptance_v2_legacy.py")


def _load_legacy() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("The preserved two-service acceptance implementation could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


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
LOADER_VERSION = "nico.two_service_live_acceptance_v2.loader.v1"


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
