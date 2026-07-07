from __future__ import annotations

from typing import Any


def _ok(value: Any) -> bool:
    return bool(value)


def setup_readiness_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    storage = payload.get("storage") or {}
    final_review = payload.get("final_review") or {}
    acceptance = payload.get("client_acceptance") or {}
    express_completion = payload.get("express_service_completion") or {}
    frontend_url = payload.get("frontend_url") or "https://app.nicoaudit.com"
    backend_url = payload.get("backend_url") or payload.get("api_url") or ""
    checks = [
        {
            "id": "frontend_deployed",
            "label": "Frontend deployed",
            "ready": _ok(frontend_url),
            "evidence": f"Frontend URL: {frontend_url}" if frontend_url else "",
            "fix": "Deploy the Vercel frontend and confirm the public URL loads.",
        },
        {
            "id": "backend_url_configured",
            "label": "Frontend points to backend",
            "ready": _ok(backend_url),
            "evidence": "Backend API URL is configured." if backend_url else "",
            "fix": "Set NEXT_PUBLIC_NICO_API_URL in Vercel to the Railway backend URL.",
        },
        {
            "id": "backend_online",
            "label": "Backend health online",
            "ready": payload.get("backend_status") == "ok" or payload.get("health", {}).get("status") == "ok",
            "evidence": "Backend health returned ok." if payload.get("backend_status") == "ok" or payload.get("health", {}).get("status") == "ok" else "",
            "fix": "Open /health on the backend and fix deployment/runtime errors until status is ok.",
        },
        {
            "id": "persistence_active",
            "label": "Persistent storage active",
            "ready": bool(storage.get("persistence_available")),
            "evidence": f"Storage adapter: {storage.get('adapter')}" if storage.get("persistence_available") else "",
            "fix": "Configure DATABASE_URL in Railway and confirm /storage/status shows persistence_available=true.",
        },
        {
            "id": "express_run_id_available",
            "label": "Express run ID available",
            "ready": _ok(payload.get("run_id") or final_review.get("run_id")),
            "evidence": f"Run ID: {payload.get('run_id') or final_review.get('run_id')}" if payload.get("run_id") or final_review.get("run_id") else "",
            "fix": "Rerun Express after the final-review target metadata deploys.",
        },
        {
            "id": "final_review_url_available",
            "label": "Final-review link available",
            "ready": _ok(final_review.get("url")),
            "evidence": f"Final-review URL: {final_review.get('url')}" if final_review.get("url") else "",
            "fix": "Rerun Express so the final_review.url field is attached.",
        },
        {
            "id": "final_review_requested",
            "label": "Final review requested",
            "ready": payload.get("final_review_status") in {"pending", "approved", "needs_more_evidence", "rejected"},
            "evidence": f"Final review status: {payload.get('final_review_status')}" if payload.get("final_review_status") else "",
            "fix": "Open /final-review using the run-scoped link and request final review.",
        },
        {
            "id": "final_review_approved",
            "label": "Final review approved",
            "ready": payload.get("final_review_status") == "approved" or acceptance.get("status") == "accepted",
            "evidence": "A same-project final review is approved." if payload.get("final_review_status") == "approved" or acceptance.get("status") == "accepted" else "",
            "fix": "Have a human reviewer approve the final report after evidence review.",
        },
        {
            "id": "acceptance_green_after_rerun",
            "label": "Acceptance green after rerun",
            "ready": acceptance.get("status") == "accepted",
            "evidence": "Client / Human Acceptance is accepted." if acceptance.get("status") == "accepted" else "",
            "fix": "Rerun Express after final-review approval so Client / Human Acceptance can turn green.",
        },
        {
            "id": "express_completion_present",
            "label": "Express service completion present",
            "ready": bool(express_completion.get("score")),
            "evidence": f"Express Service Completion: {express_completion.get('score')}/100" if express_completion.get("score") else "",
            "fix": "Attach Express Service Completion to the returned Express result.",
        },
    ]
    complete = [item for item in checks if item["ready"]]
    missing = [item for item in checks if not item["ready"]]
    score = round(len(complete) / len(checks) * 100) if checks else 0
    return {
        "status": "green" if score >= 90 else "yellow" if score >= 60 else "red",
        "score": score,
        "complete_count": len(complete),
        "total_count": len(checks),
        "complete": [item["id"] for item in complete],
        "remaining": [item["id"] for item in missing],
        "checks": checks,
        "next_setup_action": missing[0]["fix"] if missing else "Setup is ready for max-target workflow validation.",
        "rule": "Setup readiness measures deployment/configuration gates. It does not replace human review or client acceptance.",
    }
