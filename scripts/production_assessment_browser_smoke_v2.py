#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import production_assessment_browser_smoke as base


START_PATHS = {
    "express": "/assessment/express-run",
    "mid": "/assessment/mid-run",
    "full": "/assessment/full-run",
}
STATUS_PATH_RE = re.compile(r"^/assessment/(express|mid|full)-run/([^/]+)/status$")
PROXY_PREFIX = "/api/nico"


def logical_path(path: str) -> str:
    value = str(path or "")
    if value == PROXY_PREFIX:
        return "/"
    if value.startswith(f"{PROXY_PREFIX}/"):
        return value[len(PROXY_PREFIX):]
    return value


def is_assessment_path(path: str) -> bool:
    value = logical_path(path)
    return value in START_PATHS.values() or STATUS_PATH_RE.fullmatch(value) is not None


def _frontend_origin(ui: dict[str, Any], fallback: str) -> str:
    parsed = urlparse(str(ui.get("page_url") or ""))
    if parsed.scheme and parsed.hostname:
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{f':{parsed.port}' if parsed.port else ''}"
    return fallback


def _normalize_network(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items:
        normalized = deepcopy(item)
        normalized["path"] = logical_path(str(normalized.get("path") or ""))
        output.append(normalized)
    return output


def _express_exact_lifecycle(item: dict[str, Any]) -> bool:
    if item.get("tier") != "express":
        return item.get("polled_single_exact_status_url") is True
    run_id = str(item.get("initial_run_id") or "")
    expected_path = f"/assessment/express-run/{run_id}/status" if run_id else ""
    status_paths = [str(value) for value in item.get("continuation_status_paths") or []]
    continuation_ids = [str(value) for value in item.get("continuation_run_ids") or []]
    final_run_id = str(item.get("run_id") or "")
    return bool(
        run_id.startswith("express_run_")
        and final_run_id == run_id
        and status_paths
        and continuation_ids
        and all(path == expected_path for path in status_paths)
        and all(value == run_id for value in continuation_ids)
    )


def install_lifecycle_proof_compatibility() -> None:
    original_build_tier_evidence = base.build_tier_evidence
    original_run_browser_proof = base.run_browser_proof

    base.START_PATHS = START_PATHS
    base.STATUS_PATH_RE = STATUS_PATH_RE
    base.is_assessment_path = is_assessment_path

    def build_tier_evidence(
        tier: str,
        backend_origin: str,
        requests: list[dict[str, Any]],
        responses: list[dict[str, Any]],
        ui: dict[str, Any],
        screenshot: Path,
        started_at: str,
        finished_at: str,
        error: str = "",
    ) -> dict[str, Any]:
        expected_origin = _frontend_origin(ui, backend_origin)
        item = original_build_tier_evidence(
            tier,
            expected_origin,
            _normalize_network(requests),
            _normalize_network(responses),
            ui,
            screenshot,
            started_at,
            finished_at,
            error,
        )
        exact = _express_exact_lifecycle(item)
        item["polled_single_exact_status_url"] = exact
        item["network_origin_contract"] = "same_origin_frontend_proxy"
        item["logical_start_path"] = START_PATHS[tier]
        if not exact:
            item["status"] = "failed"
            item["error"] = base.safe_text(
                f"{item.get('error')}; exact {tier} lifecycle identity was not preserved".strip("; "),
                500,
            )
        return item

    def run_browser_proof(config: dict[str, Any], screenshot_dir: Path) -> dict[str, Any]:
        evidence = original_run_browser_proof(config, screenshot_dir)
        tiers = evidence.get("tiers") if isinstance(evidence.get("tiers"), list) else []
        proof = evidence.get("proof") if isinstance(evidence.get("proof"), dict) else {}
        proof["exact_run_continuation"] = bool(
            len(tiers) == 3
            and all(item.get("polled_single_exact_status_url") is True for item in tiers)
        )
        proof["same_origin_lifecycle_transport"] = bool(
            len(tiers) == 3
            and all(item.get("network_origin_contract") == "same_origin_frontend_proxy" for item in tiers)
        )
        proof["no_long_express_browser_connection"] = bool(
            len(tiers) == 3
            and any(
                item.get("tier") == "express"
                and item.get("logical_start_path") == "/assessment/express-run"
                and item.get("polled_single_exact_status_url") is True
                for item in tiers
            )
        )
        evidence["proof"] = proof
        passed = bool(
            len(tiers) == 3
            and all(value is True for value in proof.values())
            and all(item.get("status") == "passed" for item in tiers)
        )
        evidence["status"] = "passed" if passed else "failed"
        evidence["lifecycle_version"] = "express_async_v1"
        return evidence

    base.build_tier_evidence = build_tier_evidence
    base.run_browser_proof = run_browser_proof


install_lifecycle_proof_compatibility()


if __name__ == "__main__":
    try:
        raise SystemExit(base.main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
