"""Read-only proof telemetry independent of Playwright's event loop.

This observer never authorizes a release. A browser wait that stops producing
heartbeats is a failed proof, even if independent API reads find finished work.
Only bounded, allowlisted status fields and scanner gate results are retained.
"""
from __future__ import annotations

import faulthandler
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx

_ORIGINAL_CLIENT = getattr(httpx.Client, "_nico_proof_original", httpx.Client)
_RUN = re.compile(r"comprun_[a-zA-Z0-9_-]{1,100}\Z")
_WORD = re.compile(r"[a-zA-Z0-9_.:/ -]{0,180}\Z")
_ORIGIN = "https://app.nicoaudit.com"


def _word(value: Any) -> str:
    text = str(value or "")
    return text if _WORD.fullmatch(text) else "redacted_non_identifier"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


class ProofObserver:
    def __init__(self, *, origin: str, session: str, output: Path,
                 run_id: Callable[[], str], interval: float = 30,
                 stall_seconds: float = 180, client_factory: Any = None,
                 on_stall: Callable[[], None] | None = None) -> None:
        if origin.rstrip("/") != _ORIGIN or not session:
            raise ValueError("proof_observer_origin_or_session_invalid")
        if interval < 1 or stall_seconds < 2 * interval:
            raise ValueError("proof_observer_interval_invalid")
        self._origin, self._session, self._output = _ORIGIN, session, output
        self._run_id, self._interval, self._stall_seconds = run_id, interval, stall_seconds
        self._client_factory = client_factory or _ORIGINAL_CLIENT
        self._on_stall = on_stall or self._abort_ci_proof
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._waiting = False
        self._pulse_at = time.monotonic()
        self._thread: threading.Thread | None = None
        self._canonical_captured = False
        self._observations: list[dict[str, Any]] = []

    def pulse(self) -> None:
        with self._lock:
            self._pulse_at = time.monotonic()

    def watch_browser_wait(self, active: bool) -> None:
        with self._lock:
            self._waiting = active
            self._pulse_at = time.monotonic()

    def _read_json(self, client: Any, path: str, *, maximum: int) -> tuple[Any, str]:
        # Redirects are refused: a scoped session must never leave this origin.
        with client.stream("GET", self._origin + path) as response:
            if response.status_code != 200:
                raise ValueError(f"observer_http_{response.status_code}")
            raw = bytearray()
            deadline = time.monotonic() + 20
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > maximum or time.monotonic() > deadline:
                    raise ValueError("observer_response_limit")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("observer_payload_invalid")
            return value, hashlib.sha256(raw).hexdigest()

    def sample(self) -> dict[str, Any]:
        run_id = str(self._run_id() or "")
        observation: dict[str, Any] = {
            "schema": "nico.independent-proof-observer.v1", "observed_at": time.time(),
            "production_modified": False, "shipping_clearance": False,
        }
        if not _RUN.fullmatch(run_id):
            return {**observation, "status": "waiting_for_run_identity"}
        observation["run_id"] = run_id
        try:
            with self._client_factory(
                headers={"X-NICO-Operator-Session": self._session,
                         "X-NICO-Browser-Projection": "terminal-manifest-v1",
                         "Accept": "application/json", "Cache-Control": "no-store"},
                timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False,
            ) as client:
                payload, digest = self._read_json(
                    client, f"/api/nico/assessment/comprehensive-run/{run_id}", maximum=250_000)
                if payload.get("run_id") != run_id:
                    raise ValueError("observer_run_identity_mismatch")
                observation.update({
                    "status": _word(payload.get("status")),
                    "current_stage": _word(payload.get("current_stage")),
                    "terminal": payload.get("terminal") is True,
                    "human_review_required": payload.get("human_review_required") is True,
                    "client_delivery_allowed": payload.get("client_delivery_allowed") is True,
                    "status_payload_sha256": digest,
                })
                if observation["terminal"] and not self._canonical_captured:
                    canonical, canonical_digest = self._read_json(
                        client, f"/api/nico/assessment/comprehensive-run/{run_id}/report/json",
                        maximum=8_000_000)
                    from nico.complete_assessment_gate_v1 import complete_assessment_evidence
                    identity = canonical.get("identity") or {}
                    source = identity.get("commit_sha", "") if isinstance(identity, dict) else ""
                    gate = complete_assessment_evidence(canonical, expected_commit=str(source), expected_run=run_id)
                    # No finding text, client metadata, canonical report body, or credential is saved.
                    evidence = {"schema": "nico.independent-scanner-observation.v1",
                                "canonical_sha256": canonical_digest, "gate": gate,
                                "shipping_clearance": False, "browser_proof_passed": False}
                    _atomic_json(self._output.with_suffix(".scanner-observation.json"), evidence)
                    print("NICO_INDEPENDENT_SCANNER_GATE " + json.dumps(evidence, sort_keys=True), flush=True)
                    observation["independent_scanner_gate_passed"] = gate["passed"]
                    self._canonical_captured = True
        except Exception as exc:
            observation["read_error_type"] = type(exc).__name__
            if re.fullmatch(r"observer_[a-z_]+(?:_[0-9]{3})?", str(exc)):
                observation["read_error_code"] = str(exc)
            # Deliberately do not retain exception text or URLs containing response values.
        return observation

    def _abort_ci_proof(self) -> None:
        # This is a proof-runner watchdog, never a backend service kill/restart.
        if os.getenv("GITHUB_ACTIONS") != "true":
            self._stop.set()
            return
        with self._output.with_suffix(".browser-stall-stack.txt").open("w") as stream:
            faulthandler.dump_traceback(file=stream, all_threads=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        os._exit(124)

    def _loop(self) -> None:
        while not self._stop.is_set():
            observation = self.sample()
            with self._lock:
                stalled = self._waiting and time.monotonic() - self._pulse_at > self._stall_seconds
            if stalled:
                observation["proof_failure"] = "browser_wait_heartbeat_stalled"
            self._observations.append(observation)
            self._observations = self._observations[-240:]
            _atomic_json(self._output.with_suffix(".independent-observer.json"), self._observations)
            print("NICO_INDEPENDENT_OBSERVER " + json.dumps(observation, sort_keys=True), flush=True)
            if stalled:
                self._on_stall()
                return
            self._stop.wait(self._interval)

    def __enter__(self) -> "ProofObserver":
        self._thread = threading.Thread(target=self._loop, name="nico-proof-observer", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=25)
