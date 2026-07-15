from __future__ import annotations

import re
from typing import Any

REPORT_ONLY_CODE_POLICY = {
    "mode": "report_only",
    "automatic_application_allowed": False,
    "automatic_commit_allowed": False,
    "automatic_pull_request_allowed": False,
    "human_review_required": True,
    "verification_required": True,
    "accuracy_statement": (
        "A code suggestion is a review candidate, not a guaranteed fix. It must be checked against the exact "
        "repository context and pass the stated tests before adoption."
    ),
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _combined(issue: str, evidence: list[str]) -> str:
    return "\n".join([_text(issue), *(_text(item) for item in evidence)]).lower()


def _language_from_files(files: list[str]) -> str:
    suffixes = {str(item).rsplit(".", 1)[-1].lower() for item in files if "." in str(item)}
    if suffixes & {"py"}:
        return "python"
    if suffixes & {"ts", "tsx", "js", "jsx"}:
        return "typescript"
    if suffixes & {"yml", "yaml"}:
        return "yaml"
    if suffixes & {"json"}:
        return "json"
    if suffixes & {"toml", "txt"}:
        return "text"
    return "text"


def _candidate(
    *,
    category: str,
    language: str,
    title: str,
    code: str,
    conditions: list[str],
    tests: list[str],
    confidence: str = "medium",
    kind: str = "reviewable_template",
) -> dict[str, Any]:
    return {
        "status": "available",
        "mode": "report_only",
        "category": category,
        "title": title,
        "candidate_kind": kind,
        "language": language,
        "suggested_code": code.strip(),
        "confidence": confidence,
        "applicability_conditions": conditions,
        "verification_steps": tests,
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
        "verified_fix": False,
        "accuracy_statement": REPORT_ONLY_CODE_POLICY["accuracy_statement"],
    }


def unavailable_code_suggestion(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "mode": "report_only",
        "reason": _text(reason),
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
        "verified_fix": False,
        "accuracy_statement": REPORT_ONLY_CODE_POLICY["accuracy_statement"],
    }


def build_code_suggestion(
    *,
    category: str = "",
    issue: str = "",
    evidence: list[str] | None = None,
    affected_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return a bounded, report-only code candidate for known defensive patterns.

    The function intentionally does not write files, create branches, create pull
    requests, deploy, or claim that a candidate is correct for an unseen context.
    Unknown or context-sensitive findings return an unavailable candidate rather than
    fabricated replacement code.
    """

    evidence = [str(item) for item in (evidence or []) if str(item).strip()]
    affected_files = [str(item) for item in (affected_files or []) if str(item).strip()]
    combined = _combined(issue, evidence)
    normalized_category = str(category or "").strip().lower()
    language = _language_from_files(affected_files)

    if normalized_category in {"secret_exposure", "private_key", "github_token", "aws_access_key"} or "potential secret" in combined:
        return _candidate(
            category="secret_exposure",
            language="python" if language == "python" else "text",
            title="Move the secret reference to managed configuration",
            code="""
# Report-only pattern; choose the equivalent secret manager for the target platform.
import os

SERVICE_TOKEN = os.environ["SERVICE_TOKEN"]
""",
            conditions=[
                "Confirm the detected value is a real credential and not a labeled synthetic fixture.",
                "Rotate or revoke the original credential outside the source-code change.",
                "Use the target platform's secret manager rather than committing an .env file.",
            ],
            tests=[
                "Rescan the file and full git history with the configured secret scanners.",
                "Run the smallest integration test that exercises configuration loading.",
                "Confirm the old credential is revoked before closing the finding.",
            ],
            confidence="high",
        )

    if normalized_category in {"unsafe_eval", "python_eval_exec"} or re.search(r"\b(eval|exec)\s*\(", combined):
        return _candidate(
            category="unsafe_eval",
            language="python",
            title="Replace dynamic execution with an explicit parser or allowlist",
            code="""
# Use only when the input contract is a Python literal data structure.
from ast import literal_eval

parsed_value = literal_eval(untrusted_text)

# For commands or expressions, prefer an explicit allowlist instead:
ALLOWED_OPERATIONS = {"status": get_status, "summary": build_summary}
handler = ALLOWED_OPERATIONS.get(requested_operation)
if handler is None:
    raise ValueError("unsupported operation")
result = handler()
""",
            conditions=[
                "Do not substitute literal_eval when the input is intended to be executable code.",
                "Define the accepted input grammar or operation allowlist before changing behavior.",
                "Review every call site because eval and exec may have different contracts.",
            ],
            tests=[
                "Add negative tests for code-execution payloads.",
                "Add positive tests for every supported literal or allowlisted operation.",
                "Run the relevant static analyzer and application test suite.",
            ],
            confidence="medium",
        )

    if normalized_category == "python_shell_true" or "shell=true" in combined or "shell = true" in combined:
        return _candidate(
            category="command_execution",
            language="python",
            title="Pass an argument vector with shell execution disabled",
            code="""
import subprocess

# Build arguments as separate values; never concatenate untrusted input into a shell command.
command = ["executable", "--option", validated_value]
completed = subprocess.run(
    command,
    shell=False,
    check=True,
    capture_output=True,
    text=True,
    timeout=30,
)
""",
            conditions=[
                "Replace executable, options, and validation with the target command's exact contract.",
                "Confirm the existing command does not depend on shell expansion, pipes, redirects, or globbing.",
                "Apply an allowlist to any user-controlled argument.",
            ],
            tests=[
                "Add a command-injection regression test.",
                "Test expected arguments containing spaces and special characters.",
                "Run the smallest affected integration test and the security scanner.",
            ],
            confidence="high",
        )

    if normalized_category == "python_os_system" or "os.system" in combined:
        return _candidate(
            category="command_execution",
            language="python",
            title="Replace os.system with bounded subprocess execution",
            code="""
import subprocess

subprocess.run(
    ["executable", "--option", validated_value],
    shell=False,
    check=True,
    timeout=30,
)
""",
            conditions=[
                "Model the exact command as an argument list.",
                "Validate dynamic values against an explicit allowlist or strict schema.",
                "Preserve required exit-code and output handling.",
            ],
            tests=[
                "Add command-injection and timeout regression tests.",
                "Verify expected exit-code handling.",
                "Run the affected integration test and static analysis.",
            ],
            confidence="high",
        )

    if normalized_category == "unsafe_yaml_load" or "yaml.load" in combined:
        return _candidate(
            category="unsafe_deserialization",
            language="python",
            title="Use safe YAML deserialization",
            code="""
import yaml

payload = yaml.safe_load(untrusted_yaml)
""",
            conditions=[
                "Confirm the application does not intentionally deserialize custom Python objects.",
                "Validate the resulting data against an explicit schema after parsing.",
            ],
            tests=[
                "Add a malicious YAML object-construction regression test.",
                "Add schema-validation tests for expected documents.",
                "Run the affected parser tests and Bandit/Semgrep checks.",
            ],
            confidence="high",
            kind="targeted_replacement_pattern",
        )

    if normalized_category == "debug_mode" or "debug=true" in combined or "debug = true" in combined:
        return _candidate(
            category="debug_mode",
            language="python",
            title="Gate debug behavior to an explicit local-development setting",
            code="""
import os

DEBUG_ENABLED = os.getenv("APP_ENV") == "development"
app.run(debug=DEBUG_ENABLED)
""",
            conditions=[
                "Use the framework's production server and configuration mechanism in deployed environments.",
                "Confirm APP_ENV cannot be set by an untrusted request.",
            ],
            tests=[
                "Verify debug is disabled under the production deployment configuration.",
                "Verify local development can still enable debug intentionally.",
            ],
            confidence="high",
        )

    if normalized_category == "insecure_webhook" or "verify signature" in combined:
        return _candidate(
            category="webhook_authentication",
            language="python",
            title="Verify the webhook signature before processing the body",
            code="""
import hashlib
import hmac

expected = hmac.new(
    webhook_secret.encode("utf-8"),
    raw_request_body,
    hashlib.sha256,
).hexdigest()
provided = request.headers.get("X-Signature", "")
if not hmac.compare_digest(expected, provided):
    raise PermissionError("invalid webhook signature")

# Process only after signature and replay-window validation succeed.
""",
            conditions=[
                "Use the provider's documented canonical payload and signature format.",
                "Add timestamp/replay-window validation when the provider supplies a timestamp.",
                "Read the raw request body before framework parsing changes its bytes.",
            ],
            tests=[
                "Test valid, invalid, missing, and replayed signatures.",
                "Test body-byte changes invalidate the signature.",
                "Run the provider-specific integration test.",
            ],
            confidence="medium",
        )

    if normalized_category == "missing_rate_limit" or "rate limit" in combined:
        return _candidate(
            category="rate_limiting",
            language="python",
            title="Add identity-aware bounded request throttling",
            code="""
# Framework-neutral policy example for the report.
RATE_LIMIT_POLICY = {
    "window_seconds": 60,
    "max_requests": 30,
    "key": "authenticated_user_or_trusted_client_ip",
    "on_exceeded": "return_429_and_emit_security_event",
}
""",
            conditions=[
                "Use a shared backend such as Redis when multiple application instances serve traffic.",
                "Choose limits from measured traffic and endpoint sensitivity.",
                "Do not trust spoofable forwarding headers unless the proxy chain is configured.",
            ],
            tests=[
                "Test requests below, at, and above the threshold.",
                "Test independent identities do not share a bucket unexpectedly.",
                "Test limiter behavior across application instances where applicable.",
            ],
            confidence="medium",
        )

    if normalized_category == "unsafe_file_upload" or "validate upload" in combined:
        return _candidate(
            category="file_upload",
            language="python",
            title="Validate and isolate uploaded files before storage",
            code="""
from pathlib import Path
from uuid import uuid4

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}

if content_type not in ALLOWED_CONTENT_TYPES:
    raise ValueError("unsupported upload type")
if size_bytes > MAX_UPLOAD_BYTES:
    raise ValueError("upload exceeds size limit")

safe_name = f"{uuid4().hex}{Path(original_name).suffix.lower()}"
# Store outside the executable/static web root and scan before release to users.
""",
            conditions=[
                "Validate actual file signatures; do not rely only on the client-provided content type or extension.",
                "Store outside executable and directly served directories.",
                "Apply malware scanning and authorization appropriate to the product.",
            ],
            tests=[
                "Test path traversal, double extensions, oversized files, and mismatched signatures.",
                "Verify unauthorized users cannot retrieve another tenant's upload.",
                "Run upload integration and storage-isolation tests.",
            ],
            confidence="medium",
        )

    if normalized_category in {"js_inner_html", "react_dangerous_html"} or "innerhtml" in combined or "dangerouslysetinnerhtml" in combined:
        return _candidate(
            category="cross_site_scripting",
            language="typescript",
            title="Render untrusted content as text or through an audited sanitizer",
            code="""
// Prefer text rendering when HTML is not required.
element.textContent = untrustedValue;

// React: render text directly.
return <span>{untrustedValue}</span>;

// When product requirements require HTML, sanitize with an approved library and policy
// before using dangerouslySetInnerHTML; document the allowed tags and attributes.
""",
            conditions=[
                "Use text rendering unless rich HTML is an explicit requirement.",
                "Do not write a custom HTML sanitizer.",
                "Review URL, style, SVG, and event-handler handling in the sanitizer policy.",
            ],
            tests=[
                "Add XSS payload tests for script, event-handler, URL, SVG, and encoded variants.",
                "Run frontend unit tests, lint, type checks, and browser security tests.",
            ],
            confidence="medium",
        )

    if normalized_category == "tls_verify_disabled" or "verify=false" in combined or "rejectunauthorized" in combined:
        return _candidate(
            category="transport_security",
            language=language,
            title="Restore certificate verification and configure trusted certificates explicitly",
            code="""
# Python requests: certificate verification is enabled by default.
response = requests.get(url, timeout=20)

# For a private CA, provide the approved CA bundle instead of disabling verification.
response = requests.get(url, verify="/path/to/approved-ca-bundle.pem", timeout=20)
""",
            conditions=[
                "Confirm the endpoint certificate chain and hostname are correct.",
                "Use an approved CA bundle for private infrastructure.",
                "Do not add a catch-all exception that silently retries without verification.",
            ],
            tests=[
                "Verify valid certificates succeed and invalid, expired, or wrong-host certificates fail.",
                "Run the affected integration test in the deployment environment.",
            ],
            confidence="high",
        )

    if normalized_category in {"dependency_risk", "dependency_or_runtime_contract_fix"} or "missing dependency" in combined or "module not found" in combined:
        return _candidate(
            category="dependency_risk",
            language="text",
            title="Apply a bounded manifest change after resolving the verified version",
            code="""
# Python example — replace <verified-version-range> only after audit and compatibility checks.
package-name>=<minimum-fixed-version>,<next-breaking-major>

# npm example — resolve the fixed version, update the lockfile, then review the lockfile diff.
npm install package-name@<verified-fixed-version> --save-exact
""",
            conditions=[
                "Resolve the minimum fixed version from the scanner advisory or package release notes.",
                "Confirm framework and runtime compatibility before changing the manifest.",
                "Review transitive lockfile changes separately from the direct dependency edit.",
            ],
            tests=[
                "Run the dependency scanner again and require the advisory to clear.",
                "Run the smallest affected test, the full suite, and the production build.",
                "Review generated lockfile and license changes.",
            ],
            confidence="medium",
        )

    if normalized_category == "ai_agent_permission_drift" or "least privilege" in combined:
        return _candidate(
            category="ai_agent_permission_drift",
            language="python",
            title="Replace broad tool access with an explicit capability allowlist",
            code="""
ALLOWED_AGENT_ACTIONS = {
    "read_repository",
    "read_ci_results",
    "draft_report",
    "draft_repair_candidate",
}

if requested_action not in ALLOWED_AGENT_ACTIONS:
    raise PermissionError("agent action is not authorized")

if requested_action in {"draft_repair_candidate"}:
    require_human_review = True
""",
            conditions=[
                "Bind the allowlist to authenticated tenant, project, repository, and run scope.",
                "Keep production writes, deployments, credential changes, and destructive actions outside the allowlist.",
            ],
            tests=[
                "Test every allowed action and representative blocked actions.",
                "Test cross-tenant and cross-repository scope rejection.",
                "Verify audit events record the decision without exposing secrets.",
            ],
            confidence="high",
        )

    if normalized_category == "runtime_patch_surface" or "install-time patch" in combined or "compatibility module" in combined:
        return _candidate(
            category="runtime_patch_surface",
            language="python",
            title="Consolidate runtime installers behind one explicit bootstrap registry",
            code="""
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class BootstrapStep:
    name: str
    install: Callable[[], dict]

BOOTSTRAP_STEPS = (
    BootstrapStep("metadata_auth", install_metadata_auth),
    BootstrapStep("scanner_execution", install_scanner_execution),
    BootstrapStep("report_truth", install_report_truth),
)

def bootstrap_runtime() -> list[dict]:
    results = []
    for step in BOOTSTRAP_STEPS:
        outcome = step.install()
        results.append({"name": step.name, "outcome": outcome})
    return results
""",
            conditions=[
                "Migrate one installer family at a time; do not rewrite the entire bootstrap in one release.",
                "Preserve installer order, idempotency, and already-imported reference behavior with regression tests.",
                "Remove a compatibility module only after all supported import paths have migrated.",
            ],
            tests=[
                "Snapshot installer order and idempotent second-run outcomes.",
                "Run import-order, API startup, full assessment, and production smoke tests.",
                "Verify no monkey-patched reference is lost during each migration slice.",
            ],
            confidence="medium",
        )

    if normalized_category == "documentation_drift" or "documentation" in combined and "commit" in combined:
        return _candidate(
            category="documentation_drift",
            language="yaml",
            title="Generate deployed-version documentation from verified release evidence",
            code="""
# Report-only workflow pattern: update documentation only after deployment proof succeeds.
- name: Record verified deployed commit
  if: ${{ success() }}
  run: |
    python scripts/update_verified_release_doc.py \
      --commit "$GITHUB_SHA" \
      --evidence audit-results/production-release-proof.json
""",
            conditions=[
                "The updater must require exact frontend/backend commit alignment and successful production proof.",
                "Historical evidence must remain append-only; do not overwrite audit history.",
                "The documentation change still requires review before merge.",
            ],
            tests=[
                "Test stale, mismatched, failed, and missing deployment evidence are rejected.",
                "Test the updater changes only the bounded status block.",
            ],
            confidence="medium",
        )

    return unavailable_code_suggestion(
        "No conservative code template is available from the supplied evidence. The report should provide repair steps, "
        "but replacement code requires additional file context and tests."
    )


__all__ = [
    "REPORT_ONLY_CODE_POLICY",
    "build_code_suggestion",
    "unavailable_code_suggestion",
]
