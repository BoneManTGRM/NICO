#!/usr/bin/env python3
"""Prepare pinned Playwright WebKit for native tab visibility proof.

Playwright 1.61.0 marks every WebKit page proxy active and focused during page
initialization, while its target activation does not deactivate the previously
active proxy. This proof-only preparation is deliberately narrow and fail
closed: it accepts one exact upstream bundle hash, guards the unconditional
override, serializes WebKit's own active/focused state during ``bringToFront``,
and verifies the exact resulting hash. Product runtime code is not changed.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path


PLAYWRIGHT_VERSION = "1.61.0"
RUNTIME_VERSION = "nico.playwright_webkit_native_visibility.v1"
ORIGINAL_SHA256 = "6be5c2ea035554e9b184b1dbc7aa5e7f1fb428dd1b5c202022858dcfae9bee27"
PATCHED_SHA256 = "498eff53f0a286a13393671ef045fb9b54cf67b514215e40311ff50e9b574317"
ORIGINAL_INITIALIZE = """const promises = [
          this._pageProxySession.send("Dialog.enable"),
          this._pageProxySession.send("Emulation.setActiveAndFocused", { active: true })
        ];"""
PATCHED_INITIALIZE = """const promises = [
          this._pageProxySession.send("Dialog.enable")
        ];
        if (process.env.NICO_PROOF_WEBKIT_NATIVE_VISIBILITY !== "1")
          promises.push(this._pageProxySession.send("Emulation.setActiveAndFocused", { active: true }));"""
ORIGINAL_BRING_TO_FRONT = """async bringToFront() {
        await this._pageProxySession.send("Target.activate", {
          targetId: this._session.sessionId
        });
      }"""
PATCHED_BRING_TO_FRONT = """async bringToFront() {
        if (process.env.NICO_PROOF_WEBKIT_NATIVE_VISIBILITY === "1") {
          const previous = this._browserContext._nicoNativeVisibilityActivePage;
          if (previous && previous !== this)
            await previous._pageProxySession.send("Emulation.setActiveAndFocused", { active: false });
          await this._pageProxySession.send("Emulation.setActiveAndFocused", { active: true });
          this._browserContext._nicoNativeVisibilityActivePage = this;
        }
        await this._pageProxySession.send("Target.activate", {
          targetId: this._session.sessionId
        });
      }"""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bundle_path() -> Path:
    import playwright

    package = Path(playwright.__file__).resolve().parent
    return package / "driver" / "package" / "lib" / "coreBundle.js"


def prepare(bundle: Path) -> str:
    payload = bundle.read_bytes()
    observed = _sha256(payload)
    if observed == PATCHED_SHA256:
        rendered = payload.decode("utf-8")
        if (
            rendered.count(PATCHED_INITIALIZE) != 1
            or rendered.count(PATCHED_BRING_TO_FRONT) != 1
            or ORIGINAL_INITIALIZE in rendered
            or ORIGINAL_BRING_TO_FRONT in rendered
        ):
            raise RuntimeError("playwright_webkit_native_visibility_patched_shape_invalid")
        return observed
    if observed != ORIGINAL_SHA256:
        raise RuntimeError(
            "playwright_webkit_native_visibility_bundle_hash_mismatch: "
            f"expected={ORIGINAL_SHA256} observed={observed}"
        )

    rendered = payload.decode("utf-8")
    if (
        rendered.count(ORIGINAL_INITIALIZE) != 1
        or rendered.count(ORIGINAL_BRING_TO_FRONT) != 1
        or PATCHED_INITIALIZE in rendered
        or PATCHED_BRING_TO_FRONT in rendered
    ):
        raise RuntimeError("playwright_webkit_native_visibility_original_shape_invalid")
    prepared = rendered.replace(
        ORIGINAL_INITIALIZE,
        PATCHED_INITIALIZE,
        1,
    ).replace(
        ORIGINAL_BRING_TO_FRONT,
        PATCHED_BRING_TO_FRONT,
        1,
    ).encode("utf-8")
    prepared_hash = _sha256(prepared)
    if prepared_hash != PATCHED_SHA256:
        raise RuntimeError(
            "playwright_webkit_native_visibility_result_hash_mismatch: "
            f"expected={PATCHED_SHA256} observed={prepared_hash}"
        )

    temporary = bundle.with_name(f".{bundle.name}.nico-webkit-native-visibility.tmp")
    try:
        temporary.write_bytes(prepared)
        temporary.chmod(bundle.stat().st_mode)
        os.replace(temporary, bundle)
    finally:
        temporary.unlink(missing_ok=True)

    verified = bundle.read_bytes()
    if _sha256(verified) != PATCHED_SHA256:
        raise RuntimeError(
            "playwright_webkit_native_visibility_write_verification_failed"
        )
    return PATCHED_SHA256


def main() -> int:
    installed = importlib.metadata.version("playwright")
    if installed != PLAYWRIGHT_VERSION:
        raise RuntimeError(
            "playwright_webkit_native_visibility_version_mismatch: "
            f"expected={PLAYWRIGHT_VERSION} observed={installed}"
        )
    bundle = _bundle_path()
    prepared_hash = prepare(bundle)
    print(
        f"{RUNTIME_VERSION} playwright={installed} "
        f"bundle_sha256={prepared_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
