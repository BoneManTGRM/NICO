from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Mapping

from nico import comprehensive_native_providers_v3 as scoring
from nico import hosted_provider_comprehensive_runtime_v1 as hosted

VERSION = "nico.provider-control-objective-parity.v1"
_PROFILE_MARKER = "_nico_provider_control_profile_v1"
_COLLECT_MARKER = "_nico_provider_control_collect_v1"
_SCORE_MARKER = "_nico_provider_control_score_v1"

_CAPTURED_CONTROLS: ContextVar[dict[str, Any] | None] = ContextVar(
    "nico_provider_control_objective_capture_v1",
    default=None,
)

_WORKFLOW_SUFFIXES = (
    ".gitlab-ci.yml",
    "bitbucket-pipelines.yml",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
)

_CONTROL_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "cache": (
        "cache:",
        "caches:",
        "cache@",
        "restorecache@",
    ),
    "concurrency": (
        "concurrency:",
        "resource_group:",
        "lockbehavior:",
        "maxparallel:",
    ),
    "timeout": (
        "timeout-minutes:",
        "timeout:",
        "timeoutinminutes:",
    ),
    "matrix": (
        "matrix:",
        "parallel:",
        "strategy:",
    ),
    "artifact_upload": (
        "artifacts:",
        "upload-artifact",
        "publishpipelineartifact@",
        "publishbuildartifacts@",
    ),
    "environment_gate": (
        "environment:",
        "environments:",
        "deployment:",
        "manual:",
        "when: manual",
        "approval",
    ),
    "test_command": (
        "pytest",
        "npm test",
        "npm run test",
        "pnpm test",
        "yarn test",
        "dotnet test",
        "mvn test",
        "gradle test",
        "go test",
        "cargo test",
    ),
    "lint_command": (
        "npm run lint",
        "pnpm lint",
        "yarn lint",
        "eslint",
        "ruff",
        "flake8",
        "pylint",
        "mypy",
    ),
    "build_command": (
        "npm run build",
        "pnpm build",
        "yarn build",
        "next build",
        "dotnet build",
        "mvn package",
        "gradle build",
        "go build",
        "cargo build",
    ),
    "security_command": (
        "semgrep",
        "bandit",
        "gitleaks",
        "trufflehog",
        "pip-audit",
        "npm audit",
        "osv-scanner",
        "dependency-check",
        "snyk",
    ),
    "deployment_command": (
        "deploy",
        "deployment",
        "kubectl",
        "helm ",
        "terraform apply",
        "az webapp",
        "railway",
        "vercel",
    ),
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _workflow_texts(files: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw_path, raw_text in files.items():
        path = str(raw_path or "").strip()
        lowered = path.casefold()
        is_workflow = (
            lowered.endswith(_WORKFLOW_SUFFIXES)
            or (lowered.startswith(".gitlab/") and lowered.endswith((".yml", ".yaml")))
            or (lowered.startswith(".azuredevops/") and lowered.endswith((".yml", ".yaml")))
            or (lowered.startswith(".github/workflows/") and lowered.endswith((".yml", ".yaml")))
        )
        if is_workflow and isinstance(raw_text, str):
            output[path] = raw_text
    return output


def analyze_provider_neutral_workflow_controls(files: Mapping[str, Any]) -> dict[str, Any]:
    workflows = _workflow_texts(files)
    if not workflows:
        return {
            "workflow_configuration_assessed": False,
            "configuration_controls": {},
            "configuration_control_states": {
                name: "not_assessed" for name in scoring._IMMUTABLE_CONTROL_FIELDS
            },
            "workflow_paths": [],
        }

    combined = "\n".join(workflows.values()).casefold()
    controls = {
        name: any(pattern in combined for pattern in _CONTROL_PATTERNS[name])
        for name in scoring._IMMUTABLE_CONTROL_FIELDS
    }
    return {
        "workflow_configuration_assessed": True,
        "configuration_controls": controls,
        "configuration_control_states": {
            name: "assessed" for name in scoring._IMMUTABLE_CONTROL_FIELDS
        },
        "workflow_paths": sorted(workflows),
    }


def _profile_with_provider_neutral_controls(original):
    @wraps(original)
    def wrapped(repo_path):
        profile = original(repo_path)
        files = profile.get("files") if isinstance(profile, Mapping) else {}
        captured = analyze_provider_neutral_workflow_controls(
            files if isinstance(files, Mapping) else {}
        )
        _CAPTURED_CONTROLS.set(captured)
        return profile

    setattr(wrapped, _PROFILE_MARKER, True)
    setattr(wrapped, "_nico_previous", original)
    return wrapped


def _collect_with_provider_neutral_controls(original):
    @wraps(original)
    def wrapped(*args, **kwargs):
        token = _CAPTURED_CONTROLS.set(None)
        try:
            repository_evidence, complexity_evidence = original(*args, **kwargs)
            captured = _CAPTURED_CONTROLS.get()
        finally:
            _CAPTURED_CONTROLS.reset(token)

        if not isinstance(repository_evidence, dict):
            return repository_evidence, complexity_evidence
        workflow = repository_evidence.get("workflow_evidence")
        if not isinstance(workflow, dict) or not isinstance(captured, Mapping):
            return repository_evidence, complexity_evidence

        workflow["configuration_controls"] = dict(
            captured.get("configuration_controls") or {}
        )
        workflow["configuration_control_states"] = dict(
            captured.get("configuration_control_states") or {}
        )
        workflow["workflow_configuration_assessed"] = (
            captured.get("workflow_configuration_assessed") is True
        )
        workflow["provider_neutral_control_objectives"] = True
        workflow["provider_neutral_control_objective_schema"] = VERSION
        workflow["permission_control_assessed"] = False
        workflow["permission_control_state"] = "not_assessed"
        workflow["explicit_permissions_present"] = None
        return repository_evidence, complexity_evidence

    setattr(wrapped, _COLLECT_MARKER, True)
    setattr(wrapped, "_nico_previous", original)
    return wrapped


def _assessed_state(value: Any) -> bool:
    return _text(value).casefold() in {
        "assessed",
        "supported",
        "supported_limited",
        "applicable",
    }


def provider_neutral_immutable_ci_score(
    workflow: dict[str, Any],
    commit_sha: str,
) -> tuple[int, list[str], list[str], dict[str, Any]]:
    """Score equivalent immutable CI objectives without converting unknowns to failures.

    Technical performance is normalized across the objective weight that was actually
    assessed. The retained coverage percentage preserves the distinction between a
    strong assessed result and broad evidence coverage. Mutable run/job/deployment
    history remains disclosure-only and never changes this score.
    """

    workflow_files = int(workflow.get("workflow_file_count") or 0)
    configuration_sha = _text(
        workflow.get("workflow_configuration_snapshot_sha")
    ).casefold()
    expected_sha = _text(commit_sha).casefold()

    workflow_assessed = (
        workflow.get("workflow_configuration_assessed") is not False
        and ("workflow_file_count" in workflow or bool(workflow.get("workflow_files")))
    )
    exact_assessed = bool(configuration_sha and expected_sha)
    exact_configuration = bool(exact_assessed and configuration_sha == expected_sha)

    raw_permission = workflow.get("explicit_permissions_present")
    permission_state = _text(workflow.get("permission_control_state")).casefold()
    permission_assessed = (
        workflow.get("permission_control_assessed") is True
        or (isinstance(raw_permission, bool) and permission_state != "not_assessed")
    )
    explicit_permissions = raw_permission is True if permission_assessed else None

    controls = (
        workflow.get("configuration_controls")
        if isinstance(workflow.get("configuration_controls"), Mapping)
        else {}
    )
    control_states = (
        workflow.get("configuration_control_states")
        if isinstance(workflow.get("configuration_control_states"), Mapping)
        else {}
    )

    objective_states: dict[str, str] = {}
    objective_values: dict[str, bool | None] = {}
    findings: list[str] = []
    assurance_gaps: list[str] = []

    weighted: list[tuple[str, float, bool | None]] = []

    if workflow_assessed:
        value = workflow_files > 0
        objective_states["workflow_files_present"] = "passed" if value else "failed"
        objective_values["workflow_files_present"] = value
        weighted.append(("workflow_files_present", 10.0, value))
        if not value:
            findings.append("No workflow configuration was retained at the assessed commit.")
    else:
        objective_states["workflow_files_present"] = "not_assessed"
        objective_values["workflow_files_present"] = None
        weighted.append(("workflow_files_present", 10.0, None))

    if exact_assessed:
        objective_states["exact_configuration_match"] = (
            "passed" if exact_configuration else "failed"
        )
        objective_values["exact_configuration_match"] = exact_configuration
        weighted.append(("exact_configuration_match", 10.0, exact_configuration))
        if not exact_configuration:
            findings.append(
                "Workflow configuration was not proven against the exact assessed commit."
            )
    else:
        objective_states["exact_configuration_match"] = "not_assessed"
        objective_values["exact_configuration_match"] = None
        weighted.append(("exact_configuration_match", 10.0, None))

    if permission_assessed:
        value = explicit_permissions is True
        objective_states["explicit_permissions_present"] = "passed" if value else "failed"
        objective_values["explicit_permissions_present"] = value
        weighted.append(("explicit_permissions_present", 10.0, value))
        if not value:
            findings.append(
                "Explicit workflow permission boundaries were assessed and not proven at the assessed commit."
            )
    else:
        objective_states["explicit_permissions_present"] = "not_assessed"
        objective_values["explicit_permissions_present"] = None
        weighted.append(("explicit_permissions_present", 10.0, None))

    per_control_weight = 25.0 / max(1, len(scoring._IMMUTABLE_CONTROL_FIELDS))
    for name in scoring._IMMUTABLE_CONTROL_FIELDS:
        raw = controls.get(name)
        state = _text(control_states.get(name)).casefold()
        assessed = _assessed_state(state) or (
            not state and name in controls and isinstance(raw, bool)
        )
        if assessed:
            value = raw is True
            objective_states[name] = "passed" if value else "failed"
            objective_values[name] = value
            weighted.append((name, per_control_weight, value))
        else:
            objective_states[name] = "not_assessed"
            objective_values[name] = None
            weighted.append((name, per_control_weight, None))

    assessed_weight = sum(weight for _, weight, value in weighted if value is not None)
    passed_weight = sum(
        weight for _, weight, value in weighted if value is True
    )
    total_objective_weight = sum(weight for _, weight, _ in weighted)
    baseline_weight = 45.0
    denominator = baseline_weight + assessed_weight
    numerator = baseline_weight + passed_weight
    score = scoring._bounded(100.0 * numerator / denominator) if denominator else 0
    coverage = round(
        100.0 * assessed_weight / total_objective_weight
    ) if total_objective_weight else 0

    not_assessed = sorted(
        name for name, state in objective_states.items() if state == "not_assessed"
    )
    if not_assessed:
        assurance_gaps.append(
            "CI control assurance incomplete; no pass/fail claim was made for: "
            + ", ".join(not_assessed)
            + "."
        )

    historical = {
        "successful_runs": int(workflow.get("successful_runs") or 0),
        "non_success_runs": int(workflow.get("non_success_runs") or 0),
        "jobs_observed": int(workflow.get("jobs_observed") or 0),
        "job_success_rate": workflow.get("job_success_rate"),
        "deployments_observed": int(workflow.get("deployments_observed") or 0),
        "successful_deployments": int(workflow.get("successful_deployments") or 0),
        "runtime_proof_workflows": list(workflow.get("runtime_proof_workflows") or []),
        "score_effect": "none",
        "classification": "mutable_operational_trend",
    }
    evidence = [
        f"Workflow files at assessed commit: {workflow_files}.",
        f"Workflow configuration exact-SHA match: {exact_configuration if exact_assessed else 'not assessed'}.",
        f"Explicit permissions control: {objective_states['explicit_permissions_present']}.",
        f"Provider-neutral immutable CI objective coverage: {coverage}%.",
        *assurance_gaps,
        "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.",
    ]
    contract = {
        "version": VERSION,
        "configuration_snapshot_sha": configuration_sha,
        "expected_commit_sha": expected_sha,
        "exact_configuration_match": exact_configuration if exact_assessed else None,
        "provider_neutral_control_objectives": True,
        "unavailable_or_unassessed_capability_treated_as_failed": False,
        "not_assessed_capability_treated_as_passed": False,
        "objective_states": objective_states,
        "score_inputs": objective_values,
        "assessed_objective_weight": round(assessed_weight, 4),
        "total_objective_weight": round(total_objective_weight, 4),
        "control_objective_coverage_percent": coverage,
        "not_assessed_control_objectives": not_assessed,
        "mutable_operational_history_affects_technical_score": False,
        "operational_trend": historical,
    }
    return score, evidence, findings, contract


def install_provider_control_objective_parity() -> dict[str, Any]:
    current_profile = hosted._profile_checkout
    if not getattr(current_profile, _PROFILE_MARKER, False):
        hosted._profile_checkout = _profile_with_provider_neutral_controls(current_profile)

    current_collect = hosted.collect_hosted_provider_repository_evidence
    if not getattr(current_collect, _COLLECT_MARKER, False):
        hosted.collect_hosted_provider_repository_evidence = (
            _collect_with_provider_neutral_controls(current_collect)
        )

    if not getattr(scoring._immutable_ci_score, _SCORE_MARKER, False):
        setattr(provider_neutral_immutable_ci_score, _SCORE_MARKER, True)
        setattr(
            provider_neutral_immutable_ci_score,
            "_nico_previous",
            scoring._immutable_ci_score,
        )
        scoring._immutable_ci_score = provider_neutral_immutable_ci_score

    return {
        "artifact_schema": VERSION,
        "bound": scoring._immutable_ci_score is provider_neutral_immutable_ci_score,
        "hosted_profile_control_capture_bound": getattr(
            hosted._profile_checkout, _PROFILE_MARKER, False
        ) is True,
        "hosted_repository_evidence_control_binding_bound": getattr(
            hosted.collect_hosted_provider_repository_evidence,
            _COLLECT_MARKER,
            False,
        ) is True,
        "provider_neutral_control_objectives": True,
        "unavailable_or_unassessed_capability_treated_as_failed": False,
        "mutable_operational_history_affects_technical_score": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "analyze_provider_neutral_workflow_controls",
    "install_provider_control_objective_parity",
    "provider_neutral_immutable_ci_score",
]
