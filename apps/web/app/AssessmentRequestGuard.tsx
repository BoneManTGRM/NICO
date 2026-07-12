"use client";

import {useEffect, useState} from "react";

const ASSESSMENT_REQUEST_TIMEOUT_MS = 120_000;
const GUARDED_PATHS = [
  "/assessment/github",
  "/assessment/mid-run",
];

type MidReportReady = {
  runId: string;
  reportId: string;
  reportStatus: string;
  approvalId: string;
  approvalStatus: string;
  markdown: string;
  html: string;
  pdfBase64: string;
  pdfFilename: string;
  pdfSha256: string;
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function parsedRequestUrl(input: RequestInfo | URL): URL | null {
  try {
    return new URL(requestUrl(input), window.location.origin);
  } catch {
    return null;
  }
}

function isGuardedAssessmentRequest(input: RequestInfo | URL): boolean {
  const parsed = parsedRequestUrl(input);
  if (!parsed) return false;
  return GUARDED_PATHS.some((path) => parsed.pathname === path || parsed.pathname.startsWith(`${path}/`));
}

function isMidRunResponseRequest(input: RequestInfo | URL): boolean {
  const parsed = parsedRequestUrl(input);
  if (!parsed) return false;
  return parsed.pathname === "/assessment/mid-run" || /^\/assessment\/mid-run\/[^/]+\/status$/.test(parsed.pathname);
}

function decodePdf(encoded: string): Blob {
  const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
  return new Blob([bytes], {type: "application/pdf"});
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function AssessmentRequestGuard() {
  const [midReport, setMidReport] = useState<MidReportReady | null>(null);
  const [copied, setCopied] = useState("");
  const [reportError, setReportError] = useState("");

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    async function captureMidReport(response: Response) {
      if (!response.ok) return;
      try {
        const data = await response.json() as {
          assessment_type?: string;
          run_id?: string;
          report_generation_status?: string;
          reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_sha256?: string};
          mid_report?: {report_id?: string; status?: string};
          approval_request?: {approval_id?: string; status?: string};
        };
        const reports = data.reports || {};
        if (data.assessment_type !== "mid" || !reports.pdf_base64) return;
        setMidReport({
          runId: data.run_id || "",
          reportId: data.mid_report?.report_id || "",
          reportStatus: data.report_generation_status || data.mid_report?.status || "complete",
          approvalId: data.approval_request?.approval_id || "",
          approvalStatus: data.approval_request?.status || "pending",
          markdown: reports.markdown || "",
          html: reports.html || "",
          pdfBase64: reports.pdf_base64,
          pdfFilename: reports.pdf_filename || "nico-mid-assessment-DRAFT.pdf",
          pdfSha256: reports.pdf_sha256 || "",
        });
        setReportError("");
      } catch {
        // The page still handles the original response. Failure to inspect a
        // clone must never consume or replace the assessment response.
      }
    }

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const guarded = isGuardedAssessmentRequest(input);
      const capture = isMidRunResponseRequest(input);
      if (!guarded || init?.signal) {
        const response = await originalFetch(input, init);
        if (capture) void captureMidReport(response.clone());
        return response;
      }

      const controller = new AbortController();
      const timeout = window.setTimeout(() => {
        controller.abort(new Error("Assessment request exceeded two minutes. NICO stopped waiting instead of leaving the Run button spinning. Check backend status and retry."));
      }, ASSESSMENT_REQUEST_TIMEOUT_MS);

      try {
        const response = await originalFetch(input, {...init, signal: controller.signal});
        if (capture) void captureMidReport(response.clone());
        return response;
      } finally {
        window.clearTimeout(timeout);
      }
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  function downloadMidPdf() {
    if (!midReport?.pdfBase64) return;
    setReportError("");
    try {
      const blob = decodePdf(midReport.pdfBase64);
      if (!blob.size || blob.type !== "application/pdf") throw new Error("The generated Mid PDF failed browser validation.");
      saveBlob(blob, midReport.pdfFilename);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "The generated Mid PDF could not be downloaded.");
    }
  }

  async function copyReport(kind: "markdown" | "html") {
    if (!midReport) return;
    const value = kind === "markdown" ? midReport.markdown : midReport.html;
    if (!value) return;
    await navigator.clipboard?.writeText(value);
    setCopied(`${kind.toUpperCase()} copied`);
  }

  if (!midReport) return null;

  return <div className="full-run-callout" role="status" data-testid="mid-report-ready">
    <b>Mid draft report ready.</b> Run {midReport.runId || "recorded"} generated report {midReport.reportId || "recorded"}. Human review remains required{midReport.approvalId ? ` under approval ${midReport.approvalId}` : ""}; client delivery is still blocked.
    <div className="report-actions">
      <button type="button" className="primary-button" onClick={downloadMidPdf}>Download Mid draft PDF</button>
      <button type="button" disabled={!midReport.markdown} onClick={() => copyReport("markdown")}>Copy Markdown</button>
      <button type="button" disabled={!midReport.html} onClick={() => copyReport("html")}>Copy HTML</button>
      <span className="muted">Report {midReport.reportStatus} · approval {midReport.approvalStatus}{midReport.pdfSha256 ? ` · PDF ${midReport.pdfSha256.slice(0, 12)}…` : ""}</span>
      {copied ? <span className="muted">{copied}</span> : null}
    </div>
    {reportError ? <p className="error-box">{reportError}</p> : null}
  </div>;
}

export {ASSESSMENT_REQUEST_TIMEOUT_MS, GUARDED_PATHS, isMidRunResponseRequest};
