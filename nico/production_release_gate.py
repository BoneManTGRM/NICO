from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from nico.operations_readiness import OPERATIONS_READINESS_SCHEMA

PRODUCTION_RELEASE_GATE_SCHEMA = "nico.production_release_gate.v1"
FRONTEND_DEPLOYMENT_SCHEMA = "nico.frontend_deployment.v1"
REQUIRED_WORKFLOWS = (
    "NICO CI",
    "Node.js CI",
    "CodeQL Advanced",
    "Audit Evidence",
    "Security Audit Evidence",
    "Remediation Evidence",
)
REQUIRED_PROVIDERS = {
    "vercel": ("vercel",),
    "railway": ("railway",),
}
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_sha(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if _SHA_RE.fullmatch(text) else ""


def sha_matches(expected: Any, observed: Any) -> bool:
    expected_text = normalize_sha(expected)
    observed_text = str(observed or "").strip().lower()
    if not expected_text or not observed_text or observed_text == "unavailable":
        return False
    if _SHA_RE.fullmatch(observed_text):
        return observed_text == expected_text
    if re.fullmatch(r"[0-9a-f]{7,39}", observed_text):
        return expected_text.startswith(observed_text)
    return False


def safe_origin(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return f"https://{parsed.netloc}"


def _check(
    check_id: str,
    label: str,
    passed: bool,
    observed: Any,
    expected: Any,
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "required": True,
        "passed": bool(passed),
        "status": "passed" if passed else "failed",
        "observed": observed,
        "expected": expected,
        "remediation": "" if passed else remediation,
    }


def _run_order(run: dict[str, Any]) -> tuple[int, int, int]:
    def number(key: str) -> int:
        try:
            return int(run.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return number("run_number"), number("run_attempt"), number("id")


def workflow_summary(workflow_runs: list[Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw in workflow_runs:
        run = _dict(raw)
        name = str(run.get("name") or "").strip()
        if not name:
            continue
        current = latest.get(name)
        if current is None or _run_order(run) >= _run_order(current):
            latest[name] = run
    return {
        name: {
            "name": name,
            "status": str(run.get("status") or "unknown"),
            "conclusion": str(run.get("conclusion") or "unknown"),
            "event": str(run.get("event") or "unknown"),
            "head_sha": str(run.get("head_sha") or ""),
            "run_number": run.get("run_number") or 0,
            "run_attempt": run.get("run_attempt") or 0,
            "html_url": str(run.get("html_url") or ""),
        }
        for name, run in sorted(latest.items())
    }


def _provider_observations(check_runs: list[Any], commit_statuses: list[Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for raw in check_runs:
        item = _dict(raw)
        observations.append(
            {
                "source": "check_run",
                "name": str(item.get("name") or "").strip(),
                "status": str(item.get("status") or "unknown").lower(),
                "conclusion": str(item.get("conclusion") or "unknown").lower(),
                "url": str(item.get("html_url") or item.get("details_url") or ""),
            }
        )
    for raw in commit_statuses:
        item = _dict(raw)
        observations.append(
            {
                "source": "commit_status",
                "name": str(item.get("context") or item.get("name") or "").strip(),
                "status": "completed",
                "conclusion": str(item.get("state") or "unknown").lower(),
                "url": str(item.get("target_url") or ""),
            }
        )
    return [item for item in observations if item["name"]]


def provider_summary(check_runs: list[Any], commit_statuses: list[Any]) -> dict[str, dict[str, Any]]:
    observations = _provider_observations(check_runs, commit_statuses)
    result: dict[str, dict[str, Any]] = {}
    for provider, patterns in REQUIRED_PROVIDERS.items():
        matches = [
            item
            for item in observations
            if any(pattern in item["name"].lower() for pattern in patterns)
        ]
        successes = [
            item
            for item in matches
            if item["status"] == "completed" and item["conclusion"] in {"success", "neutral"}
        ]
        result[provider] = {
            "provider": provider,
            "matched": bool(matches),
            "passed": bool(successes),
            "observations": matches,
        }
    return result


def build_production_release_manifest(
    *,
    repository: str,
    expected_sha: str,
    main_head_sha: str,
    workflow_runs: list[Any],
    check_runs: list[Any],
    commit_statuses: list[Any],
    backend_readiness: dict[str, Any],
    frontend_deployment: dict[str, Any],
    backend_url: str,
    frontend_url: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    expected = normalize_sha(expected_sha)
    main_head = normalize_sha(main_head_sha)
    backend = _dict(backend_readiness)
    frontend = _dict(frontend_deployment)
    backend_origin = safe_origin(backend_url)
    frontend_origin = safe_origin(frontend_url)
    workflows = workflow_summary(workflow_runs)
    providers = provider_summary(check_runs, commit_statuses)

    backend_deployment = _dict(backend.get("deployment"))
    backend_commit = str(backend_deployment.get("deployed_commit") or "")
    frontend_commit = str(frontend.get("frontend_commit") or "")

    checks: list[dict[str, Any]] = [
        _check(
            "release_sha_valid",
            "Release SHA is a full Git commit",
            bool(expected),
            expected_sha,
            "40-character hexadecimal commit SHA",
            "Select the exact current main commit before running the production gate.",
        ),
        _check(
            "release_is_main_head",
            "Release SHA is current main head",
            bool(expected and main_head and expected == main_head),
            main_head_sha,
            expected_sha,
            "Refresh main and rerun the gate for the current main head. Do not promote a stale commit.",
        ),
        _check(
            "backend_url_secure",
            "Backend URL uses a safe HTTPS origin",
            bool(backend_origin),
            backend_origin or "invalid",
            "HTTPS origin without embedded credentials",
            "Provide the public Railway backend HTTPS origin.",
        ),
        _check(
            "frontend_url_secure",
            "Frontend URL uses a safe HTTPS origin",
            bool(frontend_origin),
            frontend_origin or "invalid",
            "HTTPS origin without embedded credentials",
            "Provide the public Vercel frontend HTTPS origin.",
        ),
    ]

    for name in REQUIRED_WORKFLOWS:
        run = workflows.get(name, {})
        passed = bool(
            run
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and sha_matches(expected, run.get("head_sha"))
        )
        checks.append(
            _check(
                f"workflow_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}",
                f"Required workflow: {name}",
                passed,
                {
                    "status": run.get("status") or "missing",
                    "conclusion": run.get("conclusion") or "missing",
                    "head_sha": run.get("head_sha") or "missing",
                },
                {"status": "completed", "conclusion": "success", "head_sha": expected or expected_sha},
                f"Run {name} for the exact release SHA and require a successful conclusion.",
            )
        )

    for provider, payload in providers.items():
        checks.append(
            _check(
                f"provider_{provider}",
                f"Deployment provider check: {provider.title()}",
                bool(payload.get("passed")),
                {
                    "matched": bool(payload.get("matched")),
                    "successful": bool(payload.get("passed")),
                    "contexts": [item.get("name") for item in _list(payload.get("observations"))],
                },
                "At least one successful provider check for the exact release commit",
                f"Complete the {provider.title()} deployment check for the exact release SHA.",
            )
        )

    checks.extend(
        [
            _check(
                "backend_readiness_schema",
                "Backend readiness schema",
                backend.get("artifact_schema") == OPERATIONS_READINESS_SCHEMA,
                backend.get("artifact_schema") or "missing",
                OPERATIONS_READINESS_SCHEMA,
                "Deploy the current backend readiness contract before promotion.",
            ),
            _check(
                "backend_semantic_readiness",
                "Backend semantic readiness",
                backend.get("status") == "ready" and backend.get("operational_ready") is True,
                {"status": backend.get("status") or "missing", "operational_ready": backend.get("operational_ready")},
                {"status": "ready", "operational_ready": True},
                "Resolve every backend operations-readiness blocker before promotion.",
            ),
            _check(
                "backend_release_sha",
                "Railway backend runs the release SHA",
                sha_matches(expected, backend_commit),
                backend_commit or "missing",
                expected or expected_sha,
                "Redeploy the Railway backend from the exact release SHA and verify runtime commit identity.",
            ),
            _check(
                "frontend_deployment_schema",
                "Frontend deployment schema",
                frontend.get("artifact_schema") == FRONTEND_DEPLOYMENT_SCHEMA,
                frontend.get("artifact_schema") or "missing",
                FRONTEND_DEPLOYMENT_SCHEMA,
                "Deploy the current frontend deployment-identity endpoint before promotion.",
            ),
            _check(
                "frontend_deployment_status",
                "Frontend deployment identity is available",
                frontend.get("status") == "ok",
                frontend.get("status") or "missing",
                "ok",
                "Configure Vercel commit identity and redeploy the frontend.",
            ),
            _check(
                "frontend_release_sha",
                "Vercel frontend runs the release SHA",
                sha_matches(expected, frontend_commit),
                frontend_commit or "missing",
                expected or expected_sha,
                "Redeploy the Vercel frontend from the exact release SHA and verify deployment identity.",
            ),
            _check(
                "frontend_backend_alignment",
                "Frontend and backend are the same release",
                bool(expected and sha_matches(expected, frontend_commit) and sha_matches(expected, backend_commit)),
                {"frontend_commit": frontend_commit or "missing", "backend_commit": backend_commit or "missing"},
                expected or expected_sha,
                "Redeploy the stale component so Vercel and Railway run the same current main commit.",
            ),
        ]
    )

    blockers = [item["id"] for item in checks if not item["passed"]]
    release_status = "ready" if not blockers else "blocked"
    stable_identity = {
        "schema": PRODUCTION_RELEASE_GATE_SCHEMA,
        "repository": str(repository or "").strip(),
        "release_sha": expected,
        "main_head_sha": main_head,
        "backend_origin": backend_origin,
        "frontend_origin": frontend_origin,
        "backend_commit": backend_commit,
        "frontend_commit": frontend_commit,
        "workflow_states": {
            name: {
                "status": _dict(workflows.get(name)).get("status") or "missing",
                "conclusion": _dict(workflows.get(name)).get("conclusion") or "missing",
                "head_sha": _dict(workflows.get(name)).get("head_sha") or "missing",
            }
            for name in REQUIRED_WORKFLOWS
        },
        "provider_states": {
            name: {
                "matched": bool(_dict(value).get("matched")),
                "passed": bool(_dict(value).get("passed")),
                "contexts": [item.get("name") for item in _list(_dict(value).get("observations"))],
            }
            for name, value in sorted(providers.items())
        },
        "backend_readiness": {
            "artifact_schema": backend.get("artifact_schema") or "missing",
            "status": backend.get("status") or "missing",
            "operational_ready": backend.get("operational_ready") is True,
            "blockers": list(backend.get("blockers") or []) if isinstance(backend.get("blockers"), list) else [],
        },
        "check_results": {item["id"]: bool(item["passed"]) for item in checks},
        "release_status": release_status,
    }
    manifest = {
        "artifact_schema": PRODUCTION_RELEASE_GATE_SCHEMA,
        "status": release_status,
        "release_ready": release_status == "ready",
        "last_known_good_eligible": release_status == "ready",
        "repository": str(repository or "").strip(),
        "release_sha": expected or str(expected_sha or ""),
        "main_head_sha": main_head or str(main_head_sha or ""),
        "generated_at": generated_at or _now(),
        "release_identity_sha256": _canonical_hash(stable_identity),
        "backend": {
            "origin": backend_origin,
            "commit": backend_commit or "missing",
            "readiness_status": backend.get("status") or "missing",
            "readiness_blockers": list(backend.get("blockers") or []) if isinstance(backend.get("blockers"), list) else [],
        },
        "frontend": {
            "origin": frontend_origin,
            "commit": frontend_commit or "missing",
            "deployment_status": frontend.get("status") or "missing",
            "provider": frontend.get("provider") or "unknown",
        },
        "workflows": workflows,
        "providers": providers,
        "checks": checks,
        "blockers": blockers,
        "next_action": (
            "Record this exact release as the production last-known-good deployment."
            if release_status == "ready"
            else "Resolve every release blocker, redeploy the exact current main commit, and rerun the complete gate."
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "This gate proves release and deployment alignment only. It does not prove repository findings are clean or authorize client delivery.",
    }
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    return manifest


__all__ = [
    "PRODUCTION_RELEASE_GATE_SCHEMA",
    "FRONTEND_DEPLOYMENT_SCHEMA",
    "REQUIRED_WORKFLOWS",
    "REQUIRED_PROVIDERS",
    "normalize_sha",
    "sha_matches",
    "safe_origin",
    "workflow_summary",
    "provider_summary",
    "build_production_release_manifest",
]
