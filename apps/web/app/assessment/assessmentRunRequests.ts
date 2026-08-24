import {copyFor} from "./assessmentCopy";
import {
  AssessmentApiError,
  apiUrl,
  parseJson,
  wait,
} from "./assessmentModel";
import type {Result} from "./assessmentTypes";

export type AssessmentRunIssue = {
  kind: "configuration_blocked" | "service_unavailable" | "run_failed";
  title: string;
  message: string;
  code: string;
  requestId: string;
  retryable: boolean;
  runCreated: boolean;
};

const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const CLIENT_RETRY_DELAYS_MS = [0, 2_000, 5_000];
const READINESS_RETRY_DELAYS_MS = [0, 2_500, 5_000];
const READINESS_PATH = "/diagnostics/comprehensive-runtime";
const INTAKE_PATH = "/assessment/comprehensive-intake";
const EXACT_SHA_RE = /^[0-9a-fA-F]{40}$/;
const READINESS_CLIENT_TIMEOUT_MS = 48_000;
// Late-stage canonical records can be materially larger than early-run projections.
// Exact-run status is idempotent recovery truth, so allow the proxy's 60s read window
// to finish and retry the GET in the browser without ever replaying continuation.
const RUN_STATUS_CLIENT_TIMEOUT_MS = 75_000;
// The server proxy gives a single non-replayable continuation up to 240s. Keep the
// browser envelope slightly larger so the proxy remains the authoritative timeout
// boundary and can return a recoverable exact-run status instruction.
const RUN_CONTINUE_CLIENT_TIMEOUT_MS = 260_000;
const RUN_STATUS_PATH = /^\/assessment\/comprehensive-run\/[^/]+$/;
const RUN_CONTINUE_PATH = /^\/assessment\/comprehensive-run\/[^/]+\/continue$/;
const BROWSER_PROJECTION_HEADER = "X-NICO-Browser-Projection";
const BROWSER_PROJECTION_VALUE = "terminal-manifest-v1";
const PERSISTENCE_BLOCK_CODES = new Set([
  "comprehensive_durable_storage_required",
  "comprehensive_sqlite_persistent_volume_required",
  "comprehensive_sqlite_storage_unavailable",
  "comprehensive_storage_not_container_replacement_safe",
]);
const BACKEND_UNAVAILABLE_CODES = new Set([
  "assessment_backend_not_configured",
  "assessment_backend_configuration_conflict",
  "assessment_backend_unreachable",
  "assessment_invalid_json",
  "assessment_readiness_timeout",
  "assessment_run_status_timeout",
  "assessment_run_continue_timeout",
]);
const RECOVERABLE_READINESS_REASONS = new Set([
  "comprehensive_database_unavailable",
]);
const PROVIDER_REPOSITORY_INPUT_CODES = new Set([
  "provider_repository_invalid",
  "provider_repository_host_not_supported",
  "provider_repository_selection_mismatch",
  "github_repository_coordinates_invalid",
  "github_repository_url_invalid",
  "gitlab_repository_coordinates_invalid",
  "gitlab_repository_url_invalid",
  "bitbucket_repository_coordinates_invalid",
  "bitbucket_repository_url_invalid",
  "azure_provider_coordinates_invalid",
  "azure_repository_url_invalid",
  "azure_repository_name_invalid",
]);
const PROVIDER_CONFIGURATION_BLOCK_CODES = new Set([
  "provider_credential_reference_missing",
  "provider_operationally_disabled",
  "provider_rollout_control_unavailable",
]);
const PROVIDER_SNAPSHOT_CODES = new Set([
  "repository_snapshot_unavailable",
  "provider_snapshot_revision_invalid",
  "provider_snapshot_revision_mismatch",
  "provider_snapshot_revision_unavailable",
]);

type AttemptResult =
  | {retry: true}
  | {retry: false; result: Result};

function browserHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  headers.set(BROWSER_PROJECTION_HEADER, BROWSER_PROJECTION_VALUE);
  return headers;
}

function bindExpectedCommitSha(path: string, init: RequestInit): RequestInit {
  const method = String(init.method || "GET").toUpperCase();
  if (path !== INTAKE_PATH || method !== "POST") {
    return init;
  }

  const raw = new URL(window.location.href).searchParams.get("expected_commit_sha");
  if (raw == null || !raw.trim()) {
    return init;
  }
  const expectedCommitSha = raw.trim().toLowerCase();
  if (!EXACT_SHA_RE.test(expectedCommitSha)) {
    throw new AssessmentApiError("The requested immutable commit SHA is invalid.", {
      status: 422,
      code: "invalid_explicit_commit_sha",
      retryable: false,
    });
  }
  if (typeof init.body !== "string") {
    throw new AssessmentApiError("The assessment intake body is unavailable for exact-commit binding.", {
      status: 422,
      code: "assessment_intake_body_unavailable",
      retryable: false,
    });
  }

  let payload: unknown;
  try {
    payload = JSON.parse(init.body);
  } catch {
    throw new AssessmentApiError("The assessment intake body is not valid JSON.", {
      status: 422,
      code: "assessment_intake_body_invalid_json",
      retryable: false,
    });
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new AssessmentApiError("The assessment intake body must be an object.", {
      status: 422,
      code: "assessment_intake_body_invalid",
      retryable: false,
    });
  }

  const body = payload as Record<string, unknown>;
  const existing = String(body.expected_commit_sha || "").trim().toLowerCase();
  if (existing && existing !== expectedCommitSha) {
    throw new AssessmentApiError("The intake commit binding conflicts with the exact release request.", {
      status: 409,
      code: "assessment_expected_commit_sha_conflict",
      retryable: false,
    });
  }

  return {
    ...init,
    body: JSON.stringify({...body, expected_commit_sha: expectedCommitSha}),
  };
}

function statusPathForContinuation(path: string): string {
  return path.replace(/\/continue$/, "");
}

function readinessReason(result: Result): string {
  return String(result.reason || "").trim().toLowerCase();
}

function readinessCanRecoverOnSameStore(result: Result): boolean {
  return RECOVERABLE_READINESS_REASONS.has(readinessReason(result))
    && result.runtime_recovery_supported === true
    && result.automatic_cross_store_fallback === false;
}

function timeoutErrorFor(
  readinessPreflight: boolean,
  runContinueRequest: boolean,
  copy: ReturnType<typeof copyFor>,
): AssessmentApiError {
  if (readinessPreflight) {
    return new AssessmentApiError(copy.serviceUnavailableMessage, {
      status: 504,
      code: "assessment_readiness_timeout",
      retryable: true,
    });
  }
  if (runContinueRequest) {
    return new AssessmentApiError(
      copy.runStatusUnavailableMessage || copy.backendError,
      {
        status: 504,
        code: "assessment_run_continue_timeout",
        retryable: true,
      },
    );
  }
  return new AssessmentApiError(
    copy.runStatusUnavailableMessage || copy.backendError,
    {
      status: 504,
      code: "assessment_run_status_timeout",
      retryable: true,
    },
  );
}

async function requestExactRunStatusWithRetry(
  path: string,
  copy: ReturnType<typeof copyFor>,
): Promise<Result> {
  // Exact-run GET retrying is centralized in requestWithRetry so every recovery path,
  // including Safari resume and Check again, gets the same bounded idempotent policy.
  return requestWithRetry(path, {method: "GET"}, copy);
}

export async function requestWithRetry(
  path: string,
  init: RequestInit,
  copy: ReturnType<typeof copyFor>,
): Promise<Result> {
  const boundInit = bindExpectedCommitSha(path, init);
  const method = String(boundInit.method || "GET").toUpperCase();
  const readinessPreflight = path === READINESS_PATH;
  const runStatusRequest = method === "GET" && RUN_STATUS_PATH.test(path);
  const runContinueRequest = method === "POST" && RUN_CONTINUE_PATH.test(path);
  // Continuation is not safely replayable. Exact-run status is idempotent durable
  // recovery truth and may retry after transient transport failure. Readiness remains
  // semantic-only and may re-probe only when parsed diagnostics prove same-store recovery.
  const boundedRequest =
    readinessPreflight || runStatusRequest || runContinueRequest;
  const requestTimeoutMs = readinessPreflight
    ? READINESS_CLIENT_TIMEOUT_MS
    : runStatusRequest
      ? RUN_STATUS_CLIENT_TIMEOUT_MS
      : runContinueRequest
        ? RUN_CONTINUE_CLIENT_TIMEOUT_MS
        : 0;
  const retryDelays = readinessPreflight
    ? READINESS_RETRY_DELAYS_MS
    : runStatusRequest
      ? CLIENT_RETRY_DELAYS_MS
      : boundedRequest
        ? [0]
        : CLIENT_RETRY_DELAYS_MS;
  let lastError: unknown = null;

  for (let attempt = 0; attempt < retryDelays.length; attempt += 1) {
    const delay = retryDelays[attempt];
    if (delay) {
      await wait(delay);
    }

    const controller = boundedRequest ? new AbortController() : null;
    let timeoutId: number | null = null;

    try {
      const requestPromise = (async (): Promise<AttemptResult> => {
        const response = await fetch(apiUrl(path), {
          ...boundInit,
          headers: browserHeaders(boundInit.headers),
          cache: "no-store",
          signal: controller?.signal || boundInit.signal,
        });
        if (
          !readinessPreflight &&
          TRANSIENT_STATUS.has(response.status) &&
          attempt < retryDelays.length - 1
        ) {
          await response.arrayBuffer();
          return {retry: true};
        }
        return {
          retry: false,
          result: await parseJson(response, copy),
        };
      })();

      let attemptResult: AttemptResult;
      if (!boundedRequest) {
        attemptResult = await requestPromise;
      } else {
        const timeoutPromise = new Promise<never>((_, reject) => {
          timeoutId = window.setTimeout(() => {
            controller?.abort();
            reject(
              timeoutErrorFor(
                readinessPreflight,
                runContinueRequest,
                copy,
              ),
            );
          }, requestTimeoutMs);
        });
        attemptResult = await Promise.race([requestPromise, timeoutPromise]);
      }

      if (!("result" in attemptResult)) {
        continue;
      }
      const result = attemptResult.result;
      if (
        readinessPreflight
        && readinessCanRecoverOnSameStore(result)
        && attempt < retryDelays.length - 1
      ) {
        continue;
      }
      if (runContinueRequest && result.terminal === true) {
        // A continuation response can race durable publication. Confirm every terminal
        // projection through idempotent exact-run status authority before React sees it.
        if (timeoutId != null) {
          window.clearTimeout(timeoutId);
          timeoutId = null;
        }
        return requestExactRunStatusWithRetry(
          statusPathForContinuation(path),
          copy,
        );
      }
      return result;
    } catch (error) {
      lastError = error;
      const retryable =
        error instanceof AssessmentApiError ? error.retryable : true;
      if (
        readinessPreflight ||
        !retryable ||
        attempt >= retryDelays.length - 1
      ) {
        break;
      }
    } finally {
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    }
  }

  if (lastError instanceof AssessmentApiError) {
    throw lastError;
  }
  if (lastError instanceof Error) {
    throw new AssessmentApiError(lastError.message || copy.backendError, {
      status: 0,
      code: "assessment_network_error",
      retryable: true,
    });
  }
  throw new AssessmentApiError(copy.backendError, {
    status: 0,
    code: "assessment_network_error",
    retryable: true,
  });
}

function spanishCopy(copy: ReturnType<typeof copyFor>): boolean {
  return copy === copyFor("es-MX");
}

function preRunIssueMessage(
  apiError: AssessmentApiError | null,
  code: string,
  copy: ReturnType<typeof copyFor>,
): string {
  const spanish = spanishCopy(copy);

  if (code === "authorized_nico_operator_required") {
    return spanish
      ? "Ingresa un token de operador NICO válido para usar GitLab, Bitbucket o Azure DevOps."
      : "Enter a valid NICO operator token to use GitLab, Bitbucket, or Azure DevOps.";
  }
  if (PROVIDER_REPOSITORY_INPUT_CODES.has(code)) {
    return spanish
      ? "La URL o el identificador del repositorio no coincide con el proveedor seleccionado. Revisa el formato y vuelve a intentarlo."
      : "The repository URL or identifier does not match the selected provider. Check the format and try again.";
  }
  if (code === "provider_credential_reference_missing") {
    return spanish
      ? "NICO no tiene configurada una credencial del servidor para este proveedor. Configúrala antes de iniciar la evaluación."
      : "NICO does not have a server-side credential configured for this provider. Configure it before starting the assessment.";
  }
  if (code === "provider_operationally_disabled") {
    return spanish
      ? "El proveedor seleccionado está deshabilitado en la configuración operativa de NICO."
      : "The selected provider is disabled in NICO's operational configuration.";
  }
  if (code === "provider_rollout_control_unavailable") {
    return spanish
      ? "El control operativo de proveedores de NICO no está disponible en este momento."
      : "NICO's provider operational control is not currently available.";
  }
  if (PROVIDER_SNAPSHOT_CODES.has(code)) {
    return spanish
      ? "NICO no pudo capturar la revisión inmutable del repositorio seleccionado. Verifica el repositorio y el acceso del proveedor."
      : "NICO could not capture the selected repository's immutable revision. Verify the repository and provider access.";
  }
  if (code === "raw_provider_credentials_prohibited") {
    return spanish
      ? "Las credenciales del proveedor deben permanecer en el servidor. No pegues tokens o contraseñas del proveedor en la solicitud."
      : "Provider credentials must remain server-side. Do not place provider tokens or passwords in the request.";
  }
  if (code === "explicit_authorization_required") {
    return spanish
      ? "Confirma la autorización del repositorio antes de crear el encargo."
      : "Confirm repository authorization before creating the engagement.";
  }
  if (code === "provider_not_supported") {
    return spanish
      ? "El proveedor seleccionado no es compatible con este flujo de evaluación."
      : "The selected provider is not supported by this assessment flow.";
  }
  if (code === "invalid_explicit_commit_sha") {
    return spanish
      ? "El SHA de commit inmutable solicitado no es válido."
      : "The requested immutable commit SHA is invalid.";
  }
  if (
    code === "assessment_intake_body_unavailable" ||
    code === "assessment_intake_body_invalid_json" ||
    code === "assessment_intake_body_invalid"
  ) {
    return spanish
      ? "La solicitud de evaluación no pudo validarse antes de crear el encargo."
      : "The assessment request could not be validated before the engagement was created.";
  }
  if (code === "assessment_expected_commit_sha_conflict") {
    return spanish
      ? "La solicitud contiene un conflicto con el commit inmutable esperado."
      : "The request conflicts with the expected immutable commit.";
  }

  // Do not leak arbitrary English backend prose into es-MX presentation. English may
  // retain the bounded backend message; Spanish falls back to its canonical copy unless
  // the error code has an approved localized presentation above.
  return spanish
    ? copy.runCreationFailureMessage
    : apiError?.message || copy.runCreationFailureMessage;
}

export function issueFor(
  caught: unknown,
  copy: ReturnType<typeof copyFor>,
  runCreated: boolean,
): AssessmentRunIssue {
  const apiError = caught instanceof AssessmentApiError ? caught : null;
  const code = String(apiError?.code || "assessment_request_failed");
  const retryable = apiError?.retryable ?? true;
  const requestId = String(apiError?.requestId || "");

  if (PERSISTENCE_BLOCK_CODES.has(code)) {
    return {
      kind: "configuration_blocked",
      title: copy.serviceUnavailableTitle,
      message: copy.storageUnavailableMessage,
      code,
      requestId,
      retryable: true,
      runCreated,
    };
  }

  if (PROVIDER_CONFIGURATION_BLOCK_CODES.has(code)) {
    return {
      kind: "configuration_blocked",
      title: copy.serviceUnavailableTitle,
      message: preRunIssueMessage(apiError, code, copy),
      code,
      requestId,
      retryable,
      runCreated,
    };
  }

  if (
    BACKEND_UNAVAILABLE_CODES.has(code) ||
    code === "assessment_network_error" ||
    (apiError?.status != null && TRANSIENT_STATUS.has(apiError.status))
  ) {
    return {
      kind: "service_unavailable",
      title: copy.serviceUnavailableTitle,
      message: runCreated
        ? copy.runStatusUnavailableMessage
        : copy.serviceUnavailableMessage,
      code,
      requestId,
      retryable,
      runCreated,
    };
  }

  // A request/control-plane error after intake is not authoritative evidence that the
  // durable assessment failed. Preserve the exact run and offer status recovery. Only
  // an explicit terminal run payload may project the run_failed state in the browser.
  if (runCreated) {
    return {
      kind: "service_unavailable",
      title: copy.serviceUnavailableTitle,
      message: copy.runStatusUnavailableMessage,
      code,
      requestId,
      retryable: true,
      runCreated: true,
    };
  }

  return {
    kind: "run_failed",
    title: copy.runFailureTitle,
    message: preRunIssueMessage(apiError, code, copy),
    code,
    requestId,
    retryable,
    runCreated: false,
  };
}
