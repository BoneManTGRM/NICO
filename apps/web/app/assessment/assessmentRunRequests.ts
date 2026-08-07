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
const READINESS_PATH = "/diagnostics/comprehensive-runtime";
const READINESS_CLIENT_TIMEOUT_MS = 48_000;
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
]);

function browserHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  headers.set(BROWSER_PROJECTION_HEADER, BROWSER_PROJECTION_VALUE);
  return headers;
}

export async function requestWithRetry(
  path: string,
  init: RequestInit,
  copy: ReturnType<typeof copyFor>,
): Promise<Result> {
  const readinessPreflight = path === READINESS_PATH;
  // The dedicated readiness route already performs its own bounded Railway
  // warm-up and authoritative diagnostic request. Repeating that complete
  // server cycle in the browser can keep mobile Safari in "Checking readiness"
  // for minutes, so readiness gets exactly one browser request.
  const retryDelays = readinessPreflight ? [0] : CLIENT_RETRY_DELAYS_MS;
  let lastError: unknown = null;
  for (let attempt = 0; attempt < retryDelays.length; attempt += 1) {
    const delay = retryDelays[attempt];
    if (delay) {
      await wait(delay);
    }

    const controller = readinessPreflight ? new AbortController() : null;
    let readinessTimedOut = false;
    const timeoutId = controller
      ? window.setTimeout(() => {
          readinessTimedOut = true;
          controller.abort();
        }, READINESS_CLIENT_TIMEOUT_MS)
      : null;

    try {
      const response = await fetch(apiUrl(path), {
        ...init,
        headers: browserHeaders(init.headers),
        cache: "no-store",
        signal: controller?.signal || init.signal,
      });
      if (
        TRANSIENT_STATUS.has(response.status) &&
        attempt < retryDelays.length - 1
      ) {
        await response.arrayBuffer();
        continue;
      }
      return await parseJson(response, copy);
    } catch (error) {
      lastError = readinessTimedOut
        ? new AssessmentApiError(copy.serviceUnavailableMessage, {
            status: 504,
            code: "assessment_readiness_timeout",
            retryable: true,
          })
        : error;
      const retryable =
        lastError instanceof AssessmentApiError ? lastError.retryable : true;
      if (!retryable || attempt >= retryDelays.length - 1) {
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

  return {
    kind: "run_failed",
    title: copy.runFailureTitle,
    message: runCreated
      ? copy.runFailureAfterCreationMessage
      : copy.runCreationFailureMessage,
    code,
    requestId,
    retryable,
    runCreated,
  };
}
