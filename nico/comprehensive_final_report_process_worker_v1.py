from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from threading import Event
from typing import Any, Mapping, MutableMapping

VERSION = "nico.comprehensive_final_report_process_worker.v1"
DEFAULT_BOOTSTRAP = "nico.api.spanish_final_report_bootstrap:app"
_CHILD_ENV = "NICO_FINAL_REPORT_ISOLATED_CHILD"


class IsolatedFinalReportCancelled(RuntimeError):
    pass


class IsolatedFinalReportWorkerError(RuntimeError):
    pass


def _bounded(value: Any, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    with temporary.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bootstrap_app(spec: str):
    module_name, separator, attribute = str(spec or "").partition(":")
    if not separator or not module_name.startswith("nico.api.") or attribute != "app":
        raise ValueError("isolated_final_report_bootstrap_invalid")
    module = importlib.import_module(module_name)
    app = getattr(module, attribute, None)
    if app is None:
        raise RuntimeError("isolated_final_report_bootstrap_app_missing")
    return app


def execute_child(input_path: Path, output_path: Path, *, bootstrap: str) -> int:
    try:
        context = _load_json(input_path)
        if not isinstance(context, dict):
            raise TypeError("isolated_final_report_context_must_be_object")
        app = _bootstrap_app(bootstrap)
        from nico.comprehensive_production_capabilities import (
            build_production_capability_executors,
        )

        executor = build_production_capability_executors(app).get(
            "final_report_generation"
        )
        if not callable(executor):
            raise RuntimeError("isolated_final_report_provider_unavailable")
        result = executor(dict(context))
        _atomic_json(
            output_path,
            {
                "kind": "result",
                "value": result,
                "worker_schema": VERSION,
                "pid": os.getpid(),
            },
        )
        return 0
    except BaseException as exc:
        payload = {
            "kind": "error",
            "error_type": type(exc).__name__,
            "error": _bounded(exc),
            "traceback": _bounded(traceback.format_exc(), 8000),
            "worker_schema": VERSION,
            "pid": os.getpid(),
        }
        try:
            _atomic_json(output_path, payload)
        except Exception:
            pass
        return 1


def terminate_process(
    process: subprocess.Popen[Any],
    *,
    grace_seconds: float = 5.0,
) -> bool:
    if process.poll() is not None:
        return True
    try:
        process.terminate()
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + max(0.1, float(grace_seconds))
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            return True
        try:
            process.wait(timeout=max(0.5, float(grace_seconds)))
        except subprocess.TimeoutExpired:
            return False
    return process.poll() is not None


def run_isolated_final_report(
    context: Mapping[str, Any],
    *,
    stop: Event,
    state: MutableMapping[str, Any],
    bootstrap: str = DEFAULT_BOOTSTRAP,
) -> tuple[Any, dict[str, Any]]:
    """Execute the production final-report provider in a killable child process.

    Input and output move through private JSON files instead of a pipe so large
    canonical evidence trees and PDF packages do not deadlock on OS pipe buffers. The
    files are created by the trusted parent process, mode 0600, and never accept
    network-supplied paths or arbitrary deserialization formats.
    """

    if os.getenv(_CHILD_ENV) == "1":
        raise RuntimeError("isolated_final_report_recursive_spawn_blocked")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="nico-final-report-") as directory:
        root = Path(directory)
        input_path = root / "context.json"
        output_path = root / "result.json"
        _atomic_json(input_path, dict(context))
        env = dict(os.environ)
        env[_CHILD_ENV] = "1"
        command = [
            sys.executable,
            "-m",
            "nico.comprehensive_final_report_process_worker_v1",
            "--child",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--bootstrap",
            bootstrap,
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            close_fds=True,
        )
        state["worker_process"] = process
        state["worker_pid"] = process.pid
        state["worker_model"] = "isolated_subprocess"
        state["worker_started_epoch"] = time.time()
        cancelled = False
        try:
            while process.poll() is None:
                if stop.wait(0.2):
                    cancelled = True
                    terminated = terminate_process(process)
                    state["worker_terminated"] = terminated
                    if not terminated:
                        raise IsolatedFinalReportWorkerError(
                            "isolated_final_report_worker_termination_failed"
                        )
                    break
            return_code = process.poll()
            if cancelled:
                raise IsolatedFinalReportCancelled(
                    "isolated_final_report_worker_cancelled"
                )
            if return_code is None:
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_exit_unknown"
                )
            if not output_path.exists():
                raise IsolatedFinalReportWorkerError(
                    f"isolated_final_report_worker_output_missing:exit={return_code}"
                )
            payload = _load_json(output_path)
            if not isinstance(payload, dict):
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_payload_invalid"
                )
            if payload.get("kind") != "result":
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_failed:"
                    + _bounded(payload.get("error_type"))
                    + ":"
                    + _bounded(payload.get("error"))
                )
            elapsed = round(time.perf_counter() - started, 3)
            return payload.get("value"), {
                "artifact_schema": VERSION,
                "worker_model": "isolated_subprocess",
                "worker_exit_code": int(return_code),
                "worker_pid": int(payload.get("pid") or process.pid or 0),
                "worker_elapsed_seconds": elapsed,
                "killable_worker": True,
                "hard_termination_supported": True,
                "pipe_free_large_result_transport": True,
                "private_file_transport": True,
            }
        finally:
            if process.poll() is None:
                state["worker_terminated"] = terminate_process(process)
            state["worker_process"] = None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap", default=DEFAULT_BOOTSTRAP)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.child or args.input is None or args.output is None:
        raise SystemExit("isolated final-report worker requires --child --input --output")
    return execute_child(args.input, args.output, bootstrap=args.bootstrap)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DEFAULT_BOOTSTRAP",
    "IsolatedFinalReportCancelled",
    "IsolatedFinalReportWorkerError",
    "VERSION",
    "execute_child",
    "run_isolated_final_report",
    "terminate_process",
]
