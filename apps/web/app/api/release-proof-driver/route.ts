import {createHash} from "node:crypto";
import {inflateSync} from "node:zlib";
import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const PRODUCTION_ORIGIN = "https://app.nicoaudit.com";
const NICO_API = `${PRODUCTION_ORIGIN}/api/nico`;
const RELEASE_SHA = "f6a3aba893e05c8b06878307a7aa14c75845654f";
const RUN_ID_RE = /^comprun_[A-Za-z0-9_-]+$/;
const PROJECTION_HEADERS = {
  Accept: "application/json",
  "Cache-Control": "no-store",
  "X-NICO-Browser-Projection": "terminal-manifest-v1",
};

const CLIENT_NAME = "NICO Acceptance Client";
const PROJECT_NAME = "NICO Acceptance Project";
const ACCESS_METHOD = "GitHub HTTPS/API - read-only";
const PRIMARY_CONTACT = "NICO Acceptance Contact";
const AUTHORIZED_SCOPE = "Full repository at exact assessed SHA - read-only";

function json(status: number, payload: Record<string, unknown>): Response {
  return Response.json(payload, {
    status,
    headers: {"Cache-Control": "no-store, private, max-age=0"},
  });
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return {raw: text.slice(0, 4000)};
  }
}

async function productionRelease(): Promise<Record<string, unknown>> {
  const response = await fetch(`${PRODUCTION_ORIGIN}/api/release`, {
    cache: "no-store",
    headers: {Accept: "application/json", "Cache-Control": "no-store"},
    signal: AbortSignal.timeout(30_000),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || !payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`production_release_unavailable:${response.status}`);
  }
  return payload as Record<string, unknown>;
}

async function nicoJson(
  path: string,
  init: RequestInit,
): Promise<{status: number; ok: boolean; body: unknown; headers: Record<string, string>}> {
  const response = await fetch(`${NICO_API}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...PROJECTION_HEADERS,
      ...(init.body ? {"Content-Type": "application/json"} : {}),
      ...(init.headers || {}),
    },
    signal: AbortSignal.timeout(245_000),
  });
  const body = await parseJsonResponse(response);
  return {
    status: response.status,
    ok: response.ok,
    body,
    headers: {
      "x-nico-run-id": response.headers.get("x-nico-run-id") || "",
      "x-request-id": response.headers.get("x-request-id") || "",
    },
  };
}

function recursiveValues(value: unknown, key: string, output: string[] = []): string[] {
  if (Array.isArray(value)) {
    for (const item of value) recursiveValues(item, key, output);
    return output;
  }
  if (!value || typeof value !== "object") return output;
  for (const [candidateKey, candidateValue] of Object.entries(value as Record<string, unknown>)) {
    if (candidateKey === key) {
      if (Array.isArray(candidateValue)) {
        for (const item of candidateValue) {
          const text = String(item || "").trim();
          if (text) output.push(text);
        }
      } else {
        const text = String(candidateValue || "").trim();
        if (text) output.push(text);
      }
    }
    recursiveValues(candidateValue, key, output);
  }
  return output;
}

function searchablePdfText(pdf: Buffer): string {
  const latin = pdf.toString("latin1");
  let searchable = latin;
  const streamPattern = /stream\r?\n/g;
  let match: RegExpExecArray | null;
  while ((match = streamPattern.exec(latin)) !== null) {
    const start = match.index + match[0].length;
    const end = latin.indexOf("endstream", start);
    if (end < 0) break;
    const dictionary = latin.slice(Math.max(0, match.index - 700), match.index);
    if (/\/FlateDecode\b/.test(dictionary)) {
      let streamEnd = end;
      while (streamEnd > start && (pdf[streamEnd - 1] === 0x0a || pdf[streamEnd - 1] === 0x0d)) {
        streamEnd -= 1;
      }
      try {
        searchable += `\n${inflateSync(pdf.subarray(start, streamEnd)).toString("latin1")}`;
      } catch {
        // Non-content Flate streams or unusual filters do not invalidate the other streams.
      }
    }
    streamPattern.lastIndex = end + "endstream".length;
  }
  return searchable;
}

function pdfPageCount(pdf: Buffer): number {
  const latin = pdf.toString("latin1");
  const direct = latin.match(/\/Type\s*\/Page\b/g)?.length || 0;
  if (direct > 0) return direct;
  const counts = [...latin.matchAll(/\/Count\s+(\d+)/g)]
    .map((item) => Number(item[1]))
    .filter((value) => Number.isInteger(value) && value > 0 && value < 5000);
  return counts.length ? Math.max(...counts) : 0;
}

async function inspectPdf(runId: string, language: "en" | "es-MX") {
  const response = await fetch(
    `${NICO_API}/assessment/comprehensive-run/${runId}/localized-report/${language}/pdf`,
    {
      cache: "no-store",
      headers: {Accept: "application/pdf", "Cache-Control": "no-store"},
      signal: AbortSignal.timeout(245_000),
    },
  );
  const pdf = Buffer.from(await response.arrayBuffer());
  const searchable = searchablePdfText(pdf);
  const metadata = {
    client: searchable.includes(CLIENT_NAME),
    project: searchable.includes(PROJECT_NAME),
    primary_contact: searchable.includes(PRIMARY_CONTACT),
  };
  const pageCount = pdfPageCount(pdf);
  return {
    status: response.status,
    ok: response.ok,
    pdf_signature: pdf.subarray(0, 4).toString("ascii") === "%PDF",
    run_id_header: response.headers.get("x-nico-run-id") || "",
    report_language_header: response.headers.get("x-nico-report-language") || "",
    assessment_rerun_header: response.headers.get("x-nico-assessment-rerun") || "",
    artifact_sha256_header: response.headers.get("x-nico-artifact-sha256") || "",
    observed_sha256: createHash("sha256").update(pdf).digest("hex"),
    size_bytes: pdf.length,
    page_count: pageCount,
    under_44_pages: pageCount > 0 && pageCount < 44,
    metadata,
    commercial_metadata_verified: Object.values(metadata).every(Boolean),
  };
}

async function inspectRun(runId: string) {
  const status = await nicoJson(`/assessment/comprehensive-run/${runId}`, {method: "GET"});
  const canonicalResponse = await fetch(
    `${NICO_API}/assessment/comprehensive-run/${runId}/report/json`,
    {
      cache: "no-store",
      headers: {Accept: "application/json", "Cache-Control": "no-store"},
      signal: AbortSignal.timeout(245_000),
    },
  );
  const canonical = await parseJsonResponse(canonicalResponse);
  const record = canonical && typeof canonical === "object" && !Array.isArray(canonical)
    ? canonical as Record<string, unknown>
    : {};
  const identity = record.identity && typeof record.identity === "object" && !Array.isArray(record.identity)
    ? record.identity as Record<string, unknown>
    : {};
  const customerName = String(identity.customer_name || identity.client_name || "");
  const projectName = String(identity.project_name || "");
  const access = recursiveValues(record, "access_method");
  const contact = recursiveValues(record, "primary_technical_contact");
  const scope = recursiveValues(record, "authorized_scope");
  const canonicalChecks = {
    run_id: String(identity.run_id || "") === runId,
    client_name: customerName === CLIENT_NAME,
    project_name: projectName === PROJECT_NAME,
    access_method: access.includes(ACCESS_METHOD),
    primary_technical_contact: contact.includes(PRIMARY_CONTACT),
    authorized_scope: scope.includes(AUTHORIZED_SCOPE),
  };
  const spanishPdf = await inspectPdf(runId, "es-MX");
  const englishPdf = await inspectPdf(runId, "en");
  return {
    status,
    canonical_http_status: canonicalResponse.status,
    identity: {
      run_id: String(identity.run_id || ""),
      customer_name: customerName,
      project_name: projectName,
    },
    canonical_values: {
      access_method: access.slice(0, 20),
      primary_technical_contact: contact.slice(0, 20),
      authorized_scope: scope.slice(0, 20),
    },
    canonical_checks: canonicalChecks,
    canonical_metadata_verified: Object.values(canonicalChecks).every(Boolean),
    spanish_pdf: spanishPdf,
    english_pdf: englishPdf,
    all_verified:
      Object.values(canonicalChecks).every(Boolean)
      && spanishPdf.ok
      && englishPdf.ok
      && spanishPdf.pdf_signature
      && englishPdf.pdf_signature
      && spanishPdf.under_44_pages
      && englishPdf.under_44_pages
      && spanishPdf.commercial_metadata_verified
      && englishPdf.commercial_metadata_verified,
  };
}

export async function GET(request: NextRequest): Promise<Response> {
  if (process.env.VERCEL_ENV !== "preview") {
    return json(404, {status: "disabled", reason: "preview_only"});
  }

  const release = await productionRelease();
  if (String(release.release_sha || "") !== RELEASE_SHA) {
    return json(409, {
      status: "blocked",
      reason: "production_release_mismatch",
      expected_sha: RELEASE_SHA,
      observed_sha: String(release.release_sha || ""),
    });
  }

  const action = request.nextUrl.searchParams.get("action") || "status";
  const runId = request.nextUrl.searchParams.get("run_id") || "";

  try {
    if (action === "start") {
      const body = {
        repository: "BoneManTGRM/NICO",
        customer_id: "nico_production_proof",
        project_id: "spanish_comprehensive_production",
        client_name: CLIENT_NAME,
        project_name: PROJECT_NAME,
        authorized_by: "nico-production-acceptance",
        authorization_reference: "synthetic-commercial-release-proof",
        authorized: true,
        timeframe_days: 180,
        assessment_depth: "strategic",
        report_language: "es-MX",
        expected_commit_sha: RELEASE_SHA,
        human_evidence: {
          stakeholder_context: {
            evidence: {
              access_method: [ACCESS_METHOD],
              primary_technical_contact: [PRIMARY_CONTACT],
              authorized_scope: [AUTHORIZED_SCOPE],
            },
            reviewer: "",
            observed_at: "",
            source_reference: "",
            excluded: false,
            exclusion_rationale: "",
          },
        },
      };
      const result = await nicoJson("/assessment/comprehensive-intake", {
        method: "POST",
        body: JSON.stringify(body),
      });
      return json(result.ok ? 200 : result.status, {
        driver: "preview-only-fixed-commercial-proof",
        action,
        expected_sha: RELEASE_SHA,
        production_release: release,
        result,
      });
    }

    if (!RUN_ID_RE.test(runId)) {
      return json(422, {status: "error", reason: "valid_run_id_required"});
    }

    if (action === "continue") {
      const result = await nicoJson(`/assessment/comprehensive-run/${runId}/continue`, {
        method: "POST",
        body: JSON.stringify({max_stages: 1}),
      });
      return json(result.ok ? 200 : result.status, {
        driver: "preview-only-fixed-commercial-proof",
        action,
        run_id: runId,
        result,
      });
    }

    if (action === "status") {
      const result = await nicoJson(`/assessment/comprehensive-run/${runId}`, {method: "GET"});
      return json(result.ok ? 200 : result.status, {
        driver: "preview-only-fixed-commercial-proof",
        action,
        run_id: runId,
        result,
      });
    }

    if (action === "inspect") {
      const proof = await inspectRun(runId);
      return json(proof.all_verified ? 200 : 409, {
        driver: "preview-only-fixed-commercial-proof",
        action,
        run_id: runId,
        expected_sha: RELEASE_SHA,
        proof,
      });
    }

    return json(404, {status: "error", reason: "unsupported_action"});
  } catch (error) {
    return json(500, {
      status: "error",
      reason: "proof_driver_exception",
      detail: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
    });
  }
}
