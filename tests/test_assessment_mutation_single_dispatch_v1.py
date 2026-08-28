from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "apps/web/app/assessment/assessmentRunRequests.ts"
PROXY = ROOT / "apps/web/app/api/nico/[...path]/route.ts"
HOOK = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"
WORKSPACE = ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx"


def test_client_never_replays_intake_continuation_or_other_mutations() -> None:
    source = CLIENT.read_text(encoding="utf-8")

    assert 'const intakeRequest = method === "POST" && path === INTAKE_PATH' in source
    assert 'const mutatingRequest = method !== "GET" && method !== "HEAD"' in source
    assert "readinessPreflight || runStatusRequest || mutatingRequest" in source
    assert ": mutatingRequest\n        ? [0]\n        : CLIENT_RETRY_DELAYS_MS" in source
    assert "const MUTATION_CLIENT_TIMEOUT_MS = 260_000" in source
    assert 'code: "assessment_intake_timeout"' in source
    assert 'code: "assessment_mutation_timeout"' in source
    assert "retryable: false" in source
    assert "No mutation is safely replayable" in source

    # Idempotent exact-run GET recovery retains its bounded browser retries.
    assert 'const runStatusRequest = method === "GET" && RUN_STATUS_PATH.test(path)' in source
    assert "runStatusRequest\n      ? CLIENT_RETRY_DELAYS_MS" in source


def test_proxy_dispatches_every_mutation_once_including_human_decisions() -> None:
    source = PROXY.read_text(encoding="utf-8")
    policy = source[source.index("function upstreamReadPolicy") : source.index("async function proxyNico")]

    assert 'const mutatingRequest = method !== "GET" && method !== "HEAD"' in policy
    assert "if (mutatingRequest)" in policy
    mutation_guard = policy.index("if (mutatingRequest)")
    generic_read = policy.index("const shortRead", mutation_guard)
    assert mutation_guard < generic_read
    mutation_policy = policy[mutation_guard:generic_read]
    assert "retryDelaysMs: SINGLE_ATTEMPT_DELAYS_MS" in mutation_policy
    assert '"single-attempt-intake"' in mutation_policy
    assert '"single-attempt-mutation"' in mutation_policy

    # These protected POST routes all flow through the mutation guard above.
    assert "COMPREHENSIVE_INTAKE" in source
    assert "COMPREHENSIVE_CONTINUE" in source
    assert "COMPREHENSIVE_REVIEW_WORK" in source
    assert "COMPREHENSIVE_REVIEW" in source
    assert "COMPREHENSIVE_AUTHORIZE_DELIVERY" in source
    assert '"The Comprehensive intake request did not complete' in source
    assert '"The protected mutation did not complete' in source
    assert "It was not replayed because" in source


def test_proxy_retries_remain_restricted_to_idempotent_get_classes() -> None:
    source = PROXY.read_text(encoding="utf-8")
    policy = source[source.index("function upstreamReadPolicy") : source.index("async function proxyNico")]

    assert 'const exactRunStatus = method === "GET"' in policy
    assert 'const shortRead = method === "GET" ||' in policy
    assert 'retryDelaysMs: RETRY_DELAYS_MS' in policy
    assert policy.index("if (mutatingRequest)") < policy.index("retryDelaysMs: RETRY_DELAYS_MS")


def test_ambiguous_intake_cannot_offer_or_invoke_one_click_replay() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    proxy = PROXY.read_text(encoding="utf-8")
    hook = HOOK.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert '"assessment_intake_outcome_unknown"' in proxy
    assert '"assessment_mutation_outcome_unknown"' in proxy
    assert "retryable: continuationFailure || (!intakeFailure && !mutationFailure)" in proxy
    assert '"assessment_intake_outcome_unknown"' in client
    assert '"assessment_mutation_outcome_unknown"' in client
    assert "retryable: !(mutatingRequest && !runContinueRequest)" in client
    assert "The assessment request may already have created a run" in client
    assert "NICO did not replay it" in client
    assert "Verifica o recupera la ejecución existente" in client

    retry_start = hook.index("async function retry(): Promise<void>")
    retry_end = hook.index("return {", retry_start)
    retry_source = hook[retry_start:retry_end]
    ambiguity_guard = retry_source.index("isAmbiguousIntakeOutcome(issue.code)")
    replay = retry_source.index("await run()")
    assert ambiguity_guard < replay
    assert "return;" in retry_source[ambiguity_guard:replay]

    assert "|| ambiguousIntakeOutcome}" in workspace
    assert 'data-assessment-reset-ambiguous-intake="true"' in workspace
    assert "I verified — reset request" in workspace
    assert "Ya verifiqué — restablecer solicitud" in workspace
    assert "preflightIssue.retryable ?" in workspace
