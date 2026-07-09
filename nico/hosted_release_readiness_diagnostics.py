from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_ROUTE_PATH = "/diagnostics/release-readiness"
REQUIRED_SUMMARY_KEYS = (
    "artifact_schema",
    "status",
    "client_delivery_allowed",
    "score",
    "target_score",
    "score_target_met",
    "green_sections",
    "yellow_sections",
    "red_sections",
    "gray_sections",
    "final_evidence_score_bridge",
    "client_final_review_gate",
    "evidence_ledger",
    "blockers",
    "guardrail",
)
REQUIRED_REPORT_EXPORT_KEYS = (
    "release_readiness_summary_json",
    "release_readiness_summary_filename",
    "release_readiness_summary_markdown",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _importable(module_name: str, symbol: str | None = None) -> bool:
    try:
        module = __import__(module_name, fromlist=[symbol] if symbol else [])
    except Exception:
        return False
    return bool(getattr(module, symbol, None)) if symbol else True


def hosted_release_readiness_diagnostics() -> dict[str, Any]:
    patch_chain = {
        "release_readiness_summary_patch": _importable("nico.release_readiness_summary_patch", "build_release_readiness_summary"),
        "final_evidence_score_bridge": _importable("nico.scanner_score_lifts", "apply_verified_scanner_score_lifts"),
        "client_final_review_gate": _importable("nico.client_final_review_gate_patch", "build_client_final_review_gate"),
        "evidence_artifact_bundle": _importable("nico.evidence_artifact_bundle", "build_evidence_artifact_bundle"),
        "report_full_detail_export": _importable("nico.report_full_detail_export_patch", "build_full_detail_export"),
    }
    missing = [name for name, available in patch_chain.items() if not available]
    return {
        "status": "ok" if not missing else "incomplete",
        "generated_at": _now_iso(),
        "route": _ROUTE_PATH,
        "purpose": "Release-readiness diagnostics for hosted reports. This reports whether readiness summary support is installed; it does not certify client delivery.",
        "patch_chain": patch_chain,
        "required_summary_keys": list(REQUIRED_SUMMARY_KEYS),
        "required_report_export_keys": list(REQUIRED_REPORT_EXPORT_KEYS),
        "summary_schema": "nico.release_readiness_summary.v1",
        "client_delivery_allowed_default": False,
        "missing_components": missing,
        "blockers": ["Missing readiness support component: " + item for item in missing],
        "guardrail": "This diagnostics endpoint never marks a report client-ready. It only confirms that release-readiness summary support is installed and describes required output fields.",
    }


def register_hosted_release_readiness_diagnostics_routes(app: Any) -> None:
    if any(getattr(route, "path", None) == _ROUTE_PATH for route in getattr(app, "routes", [])):
        return

    @app.get(_ROUTE_PATH)
    def hosted_release_readiness_diagnostics_endpoint() -> dict[str, Any]:
        return hosted_release_readiness_diagnostics()


def install_hosted_release_readiness_diagnostics_route() -> None:
    try:
        from fastapi import FastAPI
    except Exception:  # pragma: no cover - FastAPI is required in hosted app
        return
    original_init = getattr(FastAPI, "_nico_original_init_for_release_readiness_diagnostics", None)
    if original_init is None:
        original_init = FastAPI.__init__
        setattr(FastAPI, "_nico_original_init_for_release_readiness_diagnostics", original_init)

    def init_with_release_readiness_diagnostics(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        register_hosted_release_readiness_diagnostics_routes(self)

    if getattr(FastAPI.__init__, "_nico_release_readiness_diagnostics_installed", False):
        return
    init_with_release_readiness_diagnostics._nico_release_readiness_diagnostics_installed = True  # type: ignore[attr-defined]
    FastAPI.__init__ = init_with_release_readiness_diagnostics
