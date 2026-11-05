import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const SESSION_COOKIE = "nico-specialist-session";
const RETAINED_EVIDENCE_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/report\/evidence-package$/;
const STATUS_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+$/;
const SCANNER_EVIDENCE_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/scanner-evidence$/;
const CHECKOUT_RECOVERY_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/scanner-checkout-recovery$/;
const CONTINUE_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/continue$/;
const PDF_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/(?:report\/pdf|localized-report\/(?:en|es-MX)\/pdf|review-pdf\/(?:en|es-MX)\/pdf)$/;
const ARTIFACT_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/(?:report\/(?:markdown|html|json|pdf|evidence-package)|localized-report\/(?:en|es-MX)(?:\/(?:pdf|evidence-package))?|approved-delivery-package|review-pdf\/(?:en|es-MX)\/pdf)$/;
const ALLOWED_PATH = /^\/assessment\/(?:comprehensive-intake|comprehensive-run(?:\/[^/?#]+(?:\/(?:continue|review-queue|review-work|review|authorize-delivery|approved-delivery-package|automated-delivery-package|report\/(?:markdown|html|json|pdf|evidence-package)|localized-report\/(?:en|es-MX)(?:\/(?:pdf|evidence-package))?))?)?)$/;
const LOCALIZED_EDITION_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/localized-editions\/es-MX(?:\/(?:review|authorize-delivery|approved-delivery-package))?$/;
const REVIEW_PREPARATION_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/review-pdf\/(?:en|es-MX)(?:\/(?:pdf|cancel))?$/;
const RESPONSE_HEADERS = [
  "content-type", "content-length", "content-disposition", "retry-after",
  "x-nico-run-id", "x-nico-commit-sha", "x-nico-report-id", "x-nico-admission-trace",
  "x-nico-report-language", "x-nico-assessment-rerun", "x-nico-pdf-sha256",
  "x-nico-artifact-sha256", "x-nico-accepted-pdf-sha256",
  "x-nico-accepted-edition-language", "x-nico-accepted-edition-manifest-sha256",
  "x-nico-canonical-truth-sha256", "x-nico-human-review-required", "x-nico-human-review-completed",
  "x-nico-approval-status", "x-nico-delivery-status",
  "x-nico-client-delivery-allowed", "x-nico-localized-artifact-requires-new-approval",
  "x-nico-localized-artifact-approval-invalidated", "x-nico-artifact-finality", "x-nico-review-pdf-artifact-mode",
  "x-nico-frozen-source-artifact", "x-nico-delivery-package-sha256",
  "x-nico-certified-package-sha256", "x-nico-authorization-mode",
  "x-nico-human-reviewed", "x-nico-accepted-edition-sha256",
  "x-nico-delivery-certificate-sha256",
  "x-nico-evidence-manifest-sha256", "x-nico-artifact-scope", "x-nico-run-revision",
] as const;

function errorResponse(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
  return Response.json(
    {status: "blocked", detail: {code, message, ...extra}},
    {status, headers: {"Cache-Control": "no-store, private, max-age=0"}},
  );
}

function backendOrigin(): URL | null {
  const configured = [
    process.env.NICO_API_URL,
    process.env.NICO_BACKEND_URL,
    process.env.NEXT_PUBLIC_NICO_API_URL,
  ].map((value) => String(value || "").trim()).filter(Boolean);
  const origins = new Map<string, URL>();
  for (const value of configured) {
    try {
      const url = new URL(value.endsWith("/") ? value : `${value}/`);
      if (url.username || url.password || !["http:", "https:"].includes(url.protocol)) continue;
      if (process.env.NODE_ENV === "production" && url.protocol !== "https:") continue;
      origins.set(url.href, url);
    } catch {
      // Invalid origins are rejected through the bounded configuration response.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

function timeoutFor(method: string, path: string): number {
  if (method === "GET" && REVIEW_PREPARATION_PATH.test(path) && path.endsWith("/pdf")) return 240_000;
  if (method === "GET" && (ARTIFACT_PATH.test(path) || LOCALIZED_EDITION_PATH.test(path))) return 240_000;
  if (method === "GET" && STATUS_PATH.test(path)) return 60_000;
  if (method === "POST" && CONTINUE_PATH.test(path)) return 240_000;
  return method === "GET" ? 30_000 : 240_000;
}

function pdfTransferDiagnostics(startedAt: number) {
  // Never log request IDs, paths, credentials, exception text, or body content.
  const traceId = crypto.randomUUID();
  let headersMs: number | null = null;
  let firstByteMs: number | null = null;
  let bytes = 0;
  let finished = false;
  let metadata: Record<string, number | string | null> = {};
  const elapsed = () => Math.max(0, Date.now() - startedAt);
  function emit(outcome: string) {
    try {
      console.info(JSON.stringify({event: "nico_pdf_proxy_transfer", trace_id: traceId,
        outcome, elapsed_ms: elapsed(), headers_ms: headersMs,
        first_byte_read_ms: firstByteMs, upstream_body_bytes: bytes, ...metadata}));
    } catch {
      // Telemetry availability must not change artifact transport.
    }
  }
  function finish(outcome: string) {
    if (finished) return;
    finished = true;
    emit(outcome);
  }
  return {
    finish,
    wrap(response: Response, headers: Headers) {
      headersMs = elapsed();
      const length = response.headers.get("content-length") || "";
      const encoding = (response.headers.get("content-encoding") || "").trim().toLowerCase();
      const framing = (response.headers.get("transfer-encoding") || "").trim().toLowerCase();
      metadata = {upstream_status: response.status,
        declared_content_length: /^\d{1,15}$/.test(length) ? Number(length) : null,
        content_encoding: ["gzip", "br", "deflate", "identity"].includes(encoding) ? encoding : encoding ? "other" : "absent",
        transfer_encoding: framing === "chunked" ? "chunked" : framing ? "other" : "absent"};
      headers.set("X-NICO-Proxy-Trace-ID", traceId);
      headers.set("X-NICO-Proxy-Headers-Ms", String(headersMs));
      emit("headers_received");
      if (!response.body) {
        finish("no_body");
        return null;
      }
      const reader = response.body.getReader();
      return new ReadableStream<Uint8Array>({
        async pull(controller) {
          try {
            const {done, value} = await reader.read();
            if (done) {
              finish("upstream_complete");
              controller.close();
            } else {
              bytes += value.byteLength;
              if (firstByteMs === null && value.byteLength) firstByteMs = elapsed();
              controller.enqueue(value);
            }
          } catch (error) {
            finish("body_error");
            controller.error(error);
          }
        },
        async cancel(reason) {
          finish("consumer_cancelled");
          await reader.cancel(reason);
        },
      }, {highWaterMark: 0});
    },
  };
}

async function proxyAssessment(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return errorResponse(404, "nico_assessment_route_not_allowed", "The requested assessment route is unavailable.");
  }
  const path = `/assessment/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  if (!ALLOWED_PATH.test(path) && !LOCALIZED_EDITION_PATH.test(path) && !SCANNER_EVIDENCE_PATH.test(path) && !CHECKOUT_RECOVERY_PATH.test(path) && !REVIEW_PREPARATION_PATH.test(path)) {
    return errorResponse(404, "nico_assessment_route_not_allowed", "Only bounded NICO Comprehensive lifecycle routes are available.");
  }

  if (REVIEW_PREPARATION_PATH.test(path) && (
    (path.endsWith("/pdf") && request.method !== "GET")
    || (path.endsWith("/cancel") && request.method !== "POST")
    || (!path.endsWith("/pdf") && !path.endsWith("/cancel") && !["GET", "POST"].includes(request.method))
  )) return errorResponse(405, "review_pdf_method_rejected", "Use the explicit review preparation controls.");

  if (RETAINED_EVIDENCE_PATH.test(path) && request.method !== "GET") {
    return errorResponse(405, "retained_evidence_read_only", "Retained evidence download is read-only.");
  }
  if (SCANNER_EVIDENCE_PATH.test(path) && request.method !== "GET") {
    return errorResponse(405, "scanner_evidence_read_only", "Scanner evidence inventory is read-only.");
  }
  if (CHECKOUT_RECOVERY_PATH.test(path) && !["GET", "POST"].includes(request.method)) {
    return errorResponse(405, "checkout_recovery_method_rejected", "Use the explicit checkout recovery controls.");
  }

  const cookieSession = request.cookies.get(SESSION_COOKIE)?.value?.trim() || "";
  const headerSession = request.headers.get("x-nico-operator-session")?.trim() || "";
  const rawOperatorToken = request.headers.get("x-nico-admin-token")?.trim() || "";
  if (cookieSession && headerSession && cookieSession !== headerSession) {
    return errorResponse(
      409,
      "specialist_session_identity_conflict",
      "The browser and request supplied different specialist sessions.",
    );
  }
  // Cookie authority is browser-managed. Require an exact same-origin POST;
  // SameSite alone also permits sibling origins on the same site. Header-only
  // operator clients retain their existing explicit-credential transport.
  if (cookieSession && request.method === "POST" && request.headers.get("origin") !== request.nextUrl.origin) {
    return errorResponse(
      403,
      "specialist_mutation_origin_rejected",
      "Cookie-authenticated assessment changes require a same-origin request.",
    );
  }
  const session = cookieSession || headerSession;
  if (!session && !rawOperatorToken) {
    return errorResponse(401, "specialist_authentication_required", "Sign in with an authorized NICO specialist account before accessing assessment data.");
  }

  const backend = backendOrigin();
  if (!backend) {
    return errorResponse(503, "assessment_backend_not_configured", "The canonical assessment backend is unavailable or has conflicting origins.");
  }

  const headers = new Headers({Accept: request.headers.get("accept") || "application/json"});
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const browserProjection = request.headers.get("x-nico-browser-projection");
  if (browserProjection) headers.set("X-NICO-Browser-Projection", browserProjection);
  if (session) headers.set("X-NICO-Operator-Session", session);
  if (rawOperatorToken) headers.set("X-NICO-Admin-Token", rawOperatorToken);
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  headers.set("X-Request-ID", requestId);
  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();
  const upstream = new URL(`${path}${request.nextUrl.search}`, backend);
  const timeoutMs = timeoutFor(request.method, path);
  const artifactRead = request.method === "GET" && (ARTIFACT_PATH.test(path) || LOCALIZED_EDITION_PATH.test(path));
  const startedAt = Date.now();
  const pdfDiagnostics = request.method === "GET" && PDF_PATH.test(path)
    ? pdfTransferDiagnostics(startedAt) : null;

  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "no-store, private, max-age=0",
      "X-Request-ID": requestId,
      "X-NICO-Proxy-Attempts": "1",
      "X-NICO-Specialist-Access": "required",
    });
    for (const name of RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    const responseBody = pdfDiagnostics ? pdfDiagnostics.wrap(response, responseHeaders) : response.body;
    return new Response(responseBody, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    pdfDiagnostics?.finish("before_response_error");
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return errorResponse(
      timedOut ? 504 : 502,
      timedOut && artifactRead ? "assessment_artifact_timeout" : timedOut ? "assessment_backend_timeout" : "assessment_backend_unreachable",
      artifactRead
        ? "The exact-run artifact request did not complete within its single-attempt download window. Retry this download; the assessment was not rerun."
        : "The authenticated assessment request did not complete. Recover the exact run status before repeating any mutation.",
      {request_id: requestId, attempts: 1, request_class: artifactRead ? "exact-run-artifact" : "authenticated-assessment", timeout_ms: timeoutMs, elapsed_ms: Date.now() - startedAt, retryable: request.method === "GET"},
    );
  }
}

export const GET = proxyAssessment;
export const POST = proxyAssessment;
