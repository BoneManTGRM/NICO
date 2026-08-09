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
const RUN_STATUS_CLIENT_TIMEOUT_MS = 20_000;
const RUN_CONTINUE_CLIENT_TIMEOUT_MS = 90_000;
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

function statusPathForContinuation(path: string): string {
  return path.replace(/\/continue$/, "");
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
  let lastError: unknown = null;

  for (let attempt = 0; attempt < CLIENT_RETRY_DELAYS_MS.length; attempt += 1) {
    const delay = CLIENT_RETRY_DELAYS_MS[attempt];
    if (delay) {
      await wait(delay);
    }

    try {
      // Each exact-run status read remains independently bounded and idempotent.
      // This helper may retry status truth, but it can never replay continuation.
      return await requestWithRetry(path, {method: "GET"}, copy);
    } catch (error) {
      lastError = error;
      const retryable =
        error instanceof AssessmentApiError ? error.retryable : true;
      if (!retryable || attempt >= CLIENT_RETRY_DELAYS_MS.length - 1) {
        break;
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

export async function requestWithRetry(
  path: string,
  init: RequestInit,
  copy: ReturnType<typeof copyFor>,
): Promise<Result> {
  const method = String(init.method || "GET").toUpperCase();
  const readinessPreflight = path === READINESS_PATH;
  const runStatusRequest = method === "GET" && RUN_STATUS_PATH.test(path);
  const runContinueRequest = method === "POST" && RUN_CONTINUE_PATH.test(path);
  // Readiness, exact-run status, and continuation are each bounded to one browser
  // attempt. Continuation is not safely replayable. Only the dedicated helper above
  // retries idempotent exact-run status confirmation after a terminal continuation.
  const boundedRequest =
    readinessPreflight || runStatusRequest || runContinueRequest;
  const requestTimeoutMs = readinessPreflight
    ? READINESS_CLIENT_TIMEOUT_MS
    : runStatusRequest
      ? RUN_STATUS_CLIENT_TIMEOUT_MS
      : runContinueRequest
        ? RUN_CONTINUE_CLIENT_TIMEOUT_MS
        : 0;
  const retryDelays = boundedRequest ? [0] : CLIENT_RETRY_DELAYS_MS;
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
    message: copy.runCreationFailureMessage,
    code,
    requestId,
    retryable,
    runCreated: false,
  };
}
