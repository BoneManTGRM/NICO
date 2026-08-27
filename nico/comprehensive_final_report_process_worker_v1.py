from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from threading import Event
from typing import Any, Mapping, MutableMapping

VERSION = "nico.comprehensive_final_report_process_worker.v3"
DEFAULT_BOOTSTRAP = "nico.api.final_report_worker_bootstrap:app"
_CHILD_ENV = "NICO_FINAL_REPORT_ISOLATED_CHILD"
_PROCESS_GROUP_ATTR = "_nico_isolated_process_group"


class IsolatedFinalReportCancelled(RuntimeError):
    pass


class IsolatedFinalReportWorkerError(RuntimeError):
    pass


def _bounded(value: Any, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _exit_signal_name(return_code: int | None) -> str:
    if not isinstance(return_code, int) or return_code >= 0:
        return ""
    try:
        return signal.Signals(-return_code).name
    except (ValueError, TypeError):
        return f"SIGNAL_{-return_code}"


def _render_deadline_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, seconds)


def _render_deadline_state(
    *,
    started_monotonic: float,
    max_render_seconds: Any,
    now_monotonic: float | None = None,
) -> dict[str, Any]:
    deadline_seconds = _render_deadline_seconds(max_render_seconds)
    now = time.perf_counter() if now_monotonic is None else float(now_monotonic)
    elapsed = max(0.0, now - float(started_monotonic))
    active = deadline_seconds > 0.0 and float(started_monotonic) > 0.0
    return {
        "active": active,
        "overdue": active and elapsed >= deadline_seconds,
        "elapsed_seconds": elapsed,
        "deadline_seconds": deadline_seconds,
        "deadline_clock": "process_local_monotonic",
        "deadline_phase": "rendering",
    }


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(
                value,
                handle,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
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
                "bootstrap": bootstrap,
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
            "bootstrap": bootstrap,
            "pid": os.getpid(),
        }
        try:
            _atomic_json(output_path, payload)
        except Exception:
            pass
        return 1


def _isolated_process_group(process: subprocess.Popen[Any]) -> int:
    if os.name != "posix":
        return 0
    try:
        return int(getattr(process, _PROCESS_GROUP_ATTR, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _signal_worker(process: subprocess.Popen[Any], *, force: bool) -> None:
    """Signal only this isolated worker/session, never the parent web process group."""

    process_group = _isolated_process_group(process)
    if process_group:
        try:
            os.killpg(
                process_group,
                signal.SIGKILL if force else signal.SIGTERM,
            )
        except ProcessLookupError:
            pass
        else:
            return
    if process.poll() is not None:
        return
    try:
        process.kill() if force else process.terminate()
    except ProcessLookupError:
        return


def terminate_process(
    process: subprocess.Popen[Any],
    *,
    grace_seconds: float = 5.0,
) -> bool:
    """Terminate the isolated worker and its descendants, then confirm physical exit."""

    process_group = _isolated_process_group(process)
    if process.poll() is None:
        _signal_worker(process, force=False)
        deadline = time.monotonic() + max(0.1, float(grace_seconds))
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)

    # A provider may spawn descendants that survive its own SIGTERM or even outlive
    # the direct child. Because the production worker owns a dedicated process group,
    # force-clean that group before renderer capacity can be reused.
    if process_group:
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        _signal_worker(process, force=True)

    if process.poll() is None:
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
    max_render_seconds: float | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Execute the production final-report provider in a killable child process.

    Input and output move through private JSON files instead of a pipe so large
    canonical evidence trees and PDF packages do not deadlock on OS pipe buffers. The
    files are created by the trusted parent process as mode 0600 and never accept
    network-supplied paths or arbitrary deserialization formats. On POSIX the child is
    also a new process group so timeout cleanup terminates renderer descendants rather
    than only the direct Python child.

    The parent also owns a process-local monotonic renderer deadline. This is
    intentionally independent of durable lease reads and heartbeat status so a
    transient persistence failure cannot leave a renderer alive beyond the configured
    render budget. Durable lease fencing and exact-run recovery remain the coordinator's
    responsibility.

    The child imports the dedicated renderer bootstrap, not the web-process Spanish
    bootstrap. It therefore receives the exact same terminal report/language authority
    and Spanish render cache without reinstalling parent worker isolation, capacity
    hardening, or synthetic production-proof orchestration inside every render.
    """

    if os.getenv(_CHILD_ENV) == "1":
        raise RuntimeError("isolated_final_report_recursive_spawn_blocked")

    started = time.perf_counter()
    local_deadline = _render_deadline_state(
        started_monotonic=started,
        max_render_seconds=max_render_seconds,
        now_monotonic=started,
    )
    state["local_render_deadline_seconds"] = float(local_deadline["deadline_seconds"])
    state["local_render_deadline_clock"] = "process_local_monotonic"
    state["local_render_deadline_enabled"] = bool(local_deadline["active"])

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
            start_new_session=os.name == "posix",
        )
        if os.name == "posix":
            setattr(process, _PROCESS_GROUP_ATTR, process.pid)
        state["worker_process"] = process
        state["worker_pid"] = process.pid
        state["worker_model"] = "isolated_subprocess"
        state["worker_bootstrap"] = bootstrap
        state["worker_started_epoch"] = time.time()
        state["worker_process_group"] = process.pid if os.name == "posix" else 0
        cancelled = False
        try:
            while process.poll() is None:
                deadline = _render_deadline_state(
                    started_monotonic=started,
                    max_render_seconds=max_render_seconds,
                )
                if deadline["overdue"]:
                    state["deadline_expired"] = True
                    state["local_render_deadline_expired"] = True
                    state["local_render_elapsed_seconds"] = round(
                        float(deadline["elapsed_seconds"]), 3
                    )
                    terminated = terminate_process(process)
                    state["worker_terminated"] = terminated
                    if not terminated:
                        state["worker_termination_failed"] = True
                        state["worker_error_type"] = "WorkerTerminationError"
                        state["worker_error"] = (
                            "isolated_final_report_worker_deadline_termination_failed"
                        )
                        raise IsolatedFinalReportWorkerError(
                            "isolated_final_report_worker_deadline_termination_failed"
                        )
                    raise IsolatedFinalReportCancelled(
                        "isolated_final_report_worker_render_deadline_exceeded"
                    )

                wait_seconds = 0.2
                if deadline["active"]:
                    remaining = max(
                        0.01,
                        float(deadline["deadline_seconds"])
                        - float(deadline["elapsed_seconds"]),
                    )
                    wait_seconds = min(wait_seconds, remaining)

                if stop.wait(wait_seconds):
                    cancelled = True
                    terminated = terminate_process(process)
                    state["worker_terminated"] = terminated
                    if not terminated:
                        state["worker_termination_failed"] = True
                        state["worker_error_type"] = "WorkerTerminationError"
                        state["worker_error"] = (
                            "isolated_final_report_worker_termination_failed"
                        )
                        raise IsolatedFinalReportWorkerError(
                            "isolated_final_report_worker_termination_failed"
                        )
                    break

            return_code = process.poll()
            if isinstance(return_code, int):
                state["worker_exit_code"] = return_code
                state["worker_exit_signal"] = _exit_signal_name(return_code)
            if cancelled:
                raise IsolatedFinalReportCancelled(
                    "isolated_final_report_worker_cancelled"
                )

            completed_deadline = _render_deadline_state(
                started_monotonic=started,
                max_render_seconds=max_render_seconds,
            )
            if completed_deadline["overdue"]:
                state["deadline_expired"] = True
                state["local_render_deadline_expired"] = True
                state["local_render_elapsed_seconds"] = round(
                    float(completed_deadline["elapsed_seconds"]), 3
                )
                raise IsolatedFinalReportCancelled(
                    "isolated_final_report_worker_render_deadline_exceeded"
                )

            if return_code is None:
                state["worker_error_type"] = "WorkerProcessExit"
                state["worker_error"] = "isolated_final_report_worker_exit_unknown"
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_exit_unknown"
                )
            if not output_path.exists():
                signal_name = _exit_signal_name(return_code)
                detail = f"exit={return_code}"
                if signal_name:
                    detail += f":signal={signal_name}"
                state["worker_error_type"] = "WorkerProcessExit"
                state["worker_error"] = (
                    "isolated_final_report_worker_output_missing:" + detail
                )
                raise IsolatedFinalReportWorkerError(state["worker_error"])
            payload = _load_json(output_path)
            if not isinstance(payload, dict):
                state["worker_error_type"] = "WorkerPayloadError"
                state["worker_error"] = "isolated_final_report_worker_payload_invalid"
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_payload_invalid"
                )
            if payload.get("kind") != "result":
                error_type = _bounded(payload.get("error_type"), 240)
                error = _bounded(payload.get("error"), 1200)
                state["worker_error_type"] = error_type or "WorkerChildError"
                state["worker_error"] = error or "isolated_final_report_worker_failed"
                raise IsolatedFinalReportWorkerError(
                    "isolated_final_report_worker_failed:"
                    + state["worker_error_type"]
                    + ":"
                    + state["worker_error"]
                )
            elapsed = round(time.perf_counter() - started, 3)
            return payload.get("value"), {
                "artifact_schema": VERSION,
                "worker_model": "isolated_subprocess",
                "worker_bootstrap": str(payload.get("bootstrap") or bootstrap),
                "worker_exit_code": int(return_code),
                "worker_pid": int(payload.get("pid") or process.pid or 0),
                "worker_elapsed_seconds": elapsed,
                "killable_worker": True,
                "hard_termination_supported": True,
                "process_group_isolation": os.name == "posix",
                "descendant_termination_supported": os.name == "posix",
                "pipe_free_large_result_transport": True,
                "private_file_transport": True,
                "nested_web_worker_orchestration_omitted": True,
                "process_local_monotonic_deadline": bool(local_deadline["active"]),
                "render_deadline_seconds": float(local_deadline["deadline_seconds"]),
            }
        finally:
            # Run cleanup even after a normal child exit so no renderer descendant can
            # escape the dedicated process group and outlive the publication attempt.
            terminated = terminate_process(process)
            state["worker_terminated"] = terminated
            if not terminated:
                state["worker_termination_failed"] = True
            if process.poll() is None:
                # Retain the live Popen object so the parent capacity gate cannot
                # mistake an unconfirmed termination for physical worker exit.
                state["worker_process"] = process
            else:
                state["worker_process"] = None
                state["physical_worker_exit_confirmed"] = True


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
    "_render_deadline_state",
    "execute_child",
    "run_isolated_final_report",
    "terminate_process",
]
