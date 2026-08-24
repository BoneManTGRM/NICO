import type {Copy, Result} from "./assessmentTypes";

const TRANSIENT_HTTP_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const SAFE_STRING_DETAIL_CODE = /^[a-z][a-z0-9_]*$/;

export class AssessmentApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId: string;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      retryable?: boolean;
      requestId?: string;
    },
  ) {
    super(message);
    this.name = "AssessmentApiError";
    this.status = options.status;
    this.code = String(options.code || "");
    this.retryable =
      options.retryable ?? TRANSIENT_HTTP_STATUS.has(options.status);
    this.requestId = String(options.requestId || "");
  }
}

export function apiUrl(path: string): string {
  return new URL(`/api/nico${path}`, window.location.origin).href;
}

function stringDetailCode(value: unknown): string {
  if (typeof value !== "string") return "";
  const candidate = value.split(":", 1)[0].trim().toLowerCase();
  return SAFE_STRING_DETAIL_CODE.test(candidate) ? candidate : "";
}

function safeClientErrorMessage(
  data: {detail?: string | {message?: unknown; code?: unknown}; error?: string},
  copy: Copy,
  status: number,
): string {
  const stringCode = stringDetailCode(data.detail);
  if (typeof data.detail === "string") {
    // Machine diagnostics such as
    // client_engagement_context_required:access_method,... are useful for logs and
    // routing but are not client-facing prose. Keep the parsed code separately and
    // present localized bounded copy in the UI.
    return stringCode ? copy.backendError : data.detail;
  }

  const detail =
    data.detail && typeof data.detail === "object" ? data.detail : {};
  if (String(detail.code || "").trim()) {
    return copy.backendError;
  }
  return String(
    detail.message ||
      data.error ||
      `${copy.backendError} (${status})`,
  );
}

export async function parseJson(
  response: Response,
  copy: Copy,
): Promise<Result> {
  type ErrorDetail = {
    message?: unknown;
    code?: unknown;
    retryable?: unknown;
    request_id?: unknown;
  };
  let data: Result & {detail?: string | ErrorDetail; error?: string};
  try {
    data = (await response.json()) as Result & {
      detail?: string | ErrorDetail;
      error?: string;
    };
  } catch {
    throw new AssessmentApiError(copy.invalidJson, {
      status: response.status,
      code: "assessment_invalid_json",
      retryable: TRANSIENT_HTTP_STATUS.has(response.status),
      requestId: response.headers.get("x-request-id") || "",
    });
  }
  if (!response.ok) {
    const detail =
      data.detail && typeof data.detail === "object" ? data.detail : {};
    const stringCode = stringDetailCode(data.detail);
    const message = safeClientErrorMessage(data, copy, response.status);
    throw new AssessmentApiError(message, {
      status: response.status,
      code: String(
        detail.code ||
          stringCode ||
          data.error ||
          "assessment_request_failed",
      ),
      retryable:
        typeof detail.retryable === "boolean"
          ? detail.retryable
          : TRANSIENT_HTTP_STATUS.has(response.status),
      requestId: String(
        detail.request_id || response.headers.get("x-request-id") || "",
      ),
    });
  }
  return data;
}

export async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function savePdf(encoded: string, filename: string): void {
  const binary = window.atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const blob = new Blob([bytes.buffer], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
