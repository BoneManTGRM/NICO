from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from nico import durable_runtime_storage, express_async_api, storage

RUNTIME_STORAGE_TRUTH_VERSION = "nico.runtime_storage_truth.v3_renderer_truth"
_STATUS_MARKER = "_nico_runtime_storage_truth_v1"
_PERSISTENCE_MARKER = "_nico_express_persistence_truth_v1"


def _explicit_mount_verification() -> bool:
    return os.getenv("NICO_SQLITE_DURABLE_MOUNT_VERIFIED", "false").strip().lower() == "true"


def sqlite_mount_verified(path: Path) -> bool:
    if _explicit_mount_verification():
        return True
    target = path.resolve()
    try:
        if os.path.ismount(target):
            return True
        if target.exists() and target.stat().st_dev != Path("/").stat().st_dev:
            return True
    except OSError:
        return False
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            before, _separator, _after = line.partition(" - ")
            fields = before.split()
            if len(fields) < 5:
                continue
            mount_path = Path(fields[4].replace("\\040", " ")).resolve()
            if mount_path == Path("/"):
                continue
            try:
                target.relative_to(mount_path)
                return True
            except ValueError:
                continue
    except OSError:
        return False
    return False


def _wrap_status(cls: type, durability: Callable[[Any, dict[str, Any]], bool]) -> bool:
    current = cls.status
    if getattr(current, _STATUS_MARKER, False):
        return False

    def truthful_status(self: Any) -> dict[str, Any]:
        result = dict(current(self))
        verified = bool(durability(self, result))
        result["durability_verified"] = verified
        result["durable"] = verified
        if result.get("adapter") == "sqlite" and result.get("persistence_available") and not verified:
            result["persistence_note"] = (
                "SQLite lifecycle recording is writable, but deployment-survival is not verified because the configured data path is not confirmed as a persistent mount."
            )
            result["durability_warning"] = (
                "Assessment and scanner records may disappear after a container replacement until a Railway volume or Postgres database is configured."
            )
        return result

    setattr(truthful_status, _STATUS_MARKER, True)
    setattr(truthful_status, "_nico_previous", current)
    cls.status = truthful_status
    return True


def _install_express_persistence_truth() -> bool:
    current = express_async_api._persistence
    if getattr(current, _PERSISTENCE_MARKER, False):
        return False

    def truthful_persistence() -> dict[str, Any]:
        try:
            status = storage.STORE.status()
        except Exception:
            return {
                "recorded": False,
                "durable": False,
                "durability_verified": False,
                "adapter": "unknown",
                "note": "Express lifecycle storage status is unavailable.",
            }
        adapter = str(status.get("adapter") or status.get("mode") or "unknown")
        verified = bool(status.get("durability_verified", adapter == "postgres"))
        return {
            "recorded": bool(status.get("persistence_available") or adapter in {"memory", "sqlite", "postgres"}),
            "durable": verified,
            "durability_verified": verified,
            "adapter": adapter,
            "note": str(status.get("persistence_note") or "Express lifecycle state is recorded through the configured storage adapter."),
            "warning": str(status.get("durability_warning") or ""),
        }

    setattr(truthful_persistence, _PERSISTENCE_MARKER, True)
    setattr(truthful_persistence, "_nico_previous", current)
    express_async_api._persistence = truthful_persistence
    return True


def install_runtime_storage_truth() -> dict[str, Any]:
    patched = 0
    patched += int(_wrap_status(storage.MemoryAdapter, lambda _self, _result: False))
    patched += int(_wrap_status(storage.PostgresAdapter, lambda _self, result: bool(result.get("persistence_available"))))
    patched += int(
        _wrap_status(
            durable_runtime_storage.SQLiteRuntimeAdapter,
            lambda self, result: bool(result.get("persistence_available")) and sqlite_mount_verified(self.database_path.parent),
        )
    )
    persistence_patched = _install_express_persistence_truth()

    from nico.express_terminal_truth_patch import install_express_terminal_truth_patch
    from nico.express_pdf_renderer_truth_v21 import install_express_pdf_renderer_truth_v21

    terminal_truth = install_express_terminal_truth_patch()
    renderer_truth = install_express_pdf_renderer_truth_v21()
    return {
        "status": "installed"
        if patched or persistence_patched or terminal_truth.get("status") == "installed" or renderer_truth.get("status") == "installed"
        else "already_installed",
        "version": RUNTIME_STORAGE_TRUTH_VERSION,
        "status_methods_patched": patched,
        "express_persistence_patched": persistence_patched,
        "terminal_truth": terminal_truth,
        "renderer_truth": renderer_truth,
        "terminal_completion_requires_durable_record": True,
        "terminal_completion_requires_terminal_gates": True,
        "scanner_worker_evidence_mapped_to_controls": True,
        "pdf_vector_geometry_bound": True,
        "architecture_velocity_split_bound": True,
        "sqlite_writable_equals_durable": False,
        "postgres_durability_verified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "RUNTIME_STORAGE_TRUTH_VERSION",
    "install_runtime_storage_truth",
    "sqlite_mount_verified",
]
