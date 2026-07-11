"use client";

import {useEffect, useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const RUN_KEY = "nico.mid.active_run";
const TOKEN_PREFIX = "nico.mid.evidence_token.";
const RESULT_PREFIX = "nico.mid.safe_result.";

const evidenceFields = [
  ["application_url", "Application or staging URL"],
  ["ios_build_access", "iOS build access or instructions"],
  ["android_build_access", "Android build access or instructions"],
  ["architecture_documents", "Architecture documents or summary"],
  ["product_requirements", "Product requirements or summary"],
  ["stakeholder_questionnaire", "Stakeholder questionnaire"],
  ["meeting_transcripts", "Meeting transcript excerpts or summary"],
  ["existing_roadmap", "Existing roadmap or summary"],
  ["business_priorities", "Business priorities, constraints, budget, and goals"],
] as const;

type EvidenceField = (typeof evidenceFields)[number][0];
type CoverageUnit = {id?: string; label?: string; available?: boolean; status?: string; evidence?: string; limitation?: string};
type Coverage = {label?: string; calculated?: boolean; percent?: number; numerator?: number; denominator?: number; method?: string; units?: CoverageUnit[]};
type TruthSection = {
  id?: string;
  label?: string;
  truth_status?: string;
  summary?: string;
  evidence?: string[];
  unavailable?: string[];
  missing_evidence_sources?: string[];
  failed_evidence_tools?: string[];
  human_review_required?: boolean;
  direct_repository_proof?: boolean;
  score_change_allowed_without_review?: boolean;
};
type OptionalEvidence = {
  status?: string;
  fields_submitted?: string[];
  field_count?: number;
  verification_status?: string;
  direct_repository_proof?: boolean;
  score_change_allowed_without_review?: boolean;
  section_availability?: Record<string, {section?: string; status?: string; submitted_fields?: string[]; message?: string}>;
  retention_note?: string;
};
type MidResult = {
  status?: string;
  run_id?: string;
  evidence_coverage?: Coverage;
  mid_truth_status?: {
    version?: string;
    sections?: TruthSection[];
    summary?: Record<string, number>;
    review_item_ids?: string[];
    unsupported_claims_permitted?: number;
    rule?: string;
  };
  review_summary?: {
    sections_verified?: number;
    sections_verified_with_limitations?: number;
    items_require_review?: number;
    unavailable_evidence_sources?: number;
    unsupported_claims_permitted?: number;
  };
  optional_evidence?: OptionalEvidence;
  assessment?: {sections?: TruthSection[]; evidence_coverage?: Coverage};
};
type EvidenceResponse = {status?: string; optional_evidence?: OptionalEvidence; detail?: {message?: string}; error?: string};

type FormState = Record<EvidenceField, string>;

function emptyForm(): FormState {
  return Object.fromEntries(evidenceFields.map(([key]) => [key, ""])) as FormState;
}

function statusClass(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (["verified", "complete", "submitted", "ready"].includes(normalized)) return "status green";
  if (["verified with limitations", "human review required", "pending", "running"].includes(normalized)) return "status yellow";
  if (["failed", "blocked", "error"].includes(normalized)) return "status red";
  return "status gray";
}

function safeMidResult(value: unknown): MidResult | null {
  if (!value || typeof value !== "object") return null;
  const source = value as Record<string, unknown>;
  const {optional_evidence_submission: _secret, ...safe} = source;
  return safe as MidResult;
}

function responsePath(input: RequestInfo | URL): string {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return new URL(raw, window.location.origin).pathname.replace(/\/$/, "") || "/";
  } catch {
    return "";
  }
}

function isMidStatusPath(path: string) {
  return /^\/assessment\/mid-run\/midrun_[^/]+\/status$/.test(path);
}

function isMidEvidencePath(path: string) {
  return /^\/assessment\/mid-run\/midrun_[^/]+\/evidence$/.test(path);
}

function storageAvailable() {
  try {
    const key = "nico.storage.test";
    window.sessionStorage.setItem(key, "1");
    window.sessionStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export default function MidAssessmentCompanion() {
  const [active, setActive] = useState(false);
  const [runId, setRunId] = useState("");
  const [result, setResult] = useState<MidResult | null>(null);
  const [tokenAvailable, setTokenAvailable] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function retainSafeResult(value: MidResult | null, resolvedRunId: string) {
    setResult(value);
    if (!value || !resolvedRunId || !storageAvailable()) return;
    try {
      sessionStorage.setItem(RESULT_PREFIX + resolvedRunId, JSON.stringify(value));
    } catch {
      // The current in-memory result remains available when storage is full.
    }
  }

  useEffect(() => {
    const onCommandCenter = window.location.pathname === "/";
    setActive(onCommandCenter);
    if (!onCommandCenter) return;

    const canStore = storageAvailable();
    if (canStore) {
      const savedRunId = sessionStorage.getItem(RUN_KEY) || "";
      if (savedRunId.startsWith("midrun_")) {
        setRunId(savedRunId);
        setTokenAvailable(Boolean(sessionStorage.getItem(TOKEN_PREFIX + savedRunId)));
        const savedResult = sessionStorage.getItem(RESULT_PREFIX + savedRunId);
        if (savedResult) {
          try {
            setResult(safeMidResult(JSON.parse(savedResult)));
          } catch {
            sessionStorage.removeItem(RESULT_PREFIX + savedRunId);
          }
        }
      }
    }

    const originalFetch = window.fetch.bind(window);
    const wrappedFetch: typeof window.fetch = async (input, init) => {
      const response = await originalFetch(input, init);
      const path = responsePath(input);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      const targeted = method === "POST" && (path === "/assessment/mid-run" || isMidStatusPath(path) || isMidEvidencePath(path));
      if (!targeted || !response.ok) return response;
      try {
        const data = await response.clone().json() as Record<string, unknown>;
        if (path === "/assessment/mid-run" || isMidStatusPath(path)) {
          const resolvedRunId = String(data.run_id || "");
          if (resolvedRunId.startsWith("midrun_")) {
            const submission = data.optional_evidence_submission as {token?: unknown} | undefined;
            const token = String(submission?.token || "");
            if (canStore) {
              sessionStorage.setItem(RUN_KEY, resolvedRunId);
              if (token) sessionStorage.setItem(TOKEN_PREFIX + resolvedRunId, token);
            }
            setRunId(resolvedRunId);
            setTokenAvailable(token ? true : canStore && Boolean(sessionStorage.getItem(TOKEN_PREFIX + resolvedRunId)));
            retainSafeResult(safeMidResult(data), resolvedRunId);
            setMessage(token ? "Additional-evidence capability retained in this browser session." : "Mid status updated.");
          }
        } else if (isMidEvidencePath(path)) {
          const evidence = data.optional_evidence as OptionalEvidence | undefined;
          if (evidence) {
            setResult((current) => {
              const updated = {...(current || {}), optional_evidence: evidence};
              if (runId && canStore) sessionStorage.setItem(RESULT_PREFIX + runId, JSON.stringify(updated));
              return updated;
            });
          }
        }
      } catch {
        // A successful non-JSON response should not affect the command center.
      }
      return response;
    };
    window.fetch = wrappedFetch;
    return () => {
      if (window.fetch === wrappedFetch) window.fetch = originalFetch;
    };
  }, []);

  const coverage = result?.evidence_coverage || result?.assessment?.evidence_coverage;
  const sections = result?.mid_truth_status?.sections || result?.assessment?.sections || [];
  const reviewSummary = result?.review_summary;
  const optional = result?.optional_evidence;
  const verified = useMemo(() => sections.filter((item) => item.truth_status === "Verified"), [sections]);
  const exceptions = useMemo(() => sections.filter((item) => item.truth_status !== "Verified"), [sections]);

  function setField(key: EvidenceField, value: string) {
    setForm((current) => ({...current, [key]: value}));
  }

  async function submitEvidence() {
    if (!API_URL || !runId || !tokenAvailable || submitting) return;
    setError("");
    setMessage("");
    const token = storageAvailable() ? sessionStorage.getItem(TOKEN_PREFIX + runId) || "" : "";
    if (!token) {
      setTokenAvailable(false);
      setError("The one-time submission capability is not available in this browser session. Start a fresh Mid run to issue a new capability.");
      return;
    }
    const fields = Object.fromEntries(Object.entries(form).filter(([, value]) => value.trim())) as Partial<FormState>;
    if (!Object.keys(fields).length) {
      setError("Add at least one optional evidence item before submitting.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId)}/evidence`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token, ...fields}),
        cache: "no-store",
        referrerPolicy: "no-referrer",
      });
      const data = await response.json() as EvidenceResponse;
      if (!response.ok || data.status !== "submitted" || !data.optional_evidence) {
        throw new Error(data.detail?.message || data.error || "Optional evidence submission was blocked.");
      }
      const updated = {...(result || {}), optional_evidence: data.optional_evidence};
      retainSafeResult(updated, runId);
      setForm(emptyForm());
      setMessage("Optional context was attached to the exact Mid run and remains human-review-bound.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Optional evidence submission failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function forgetCapability() {
    if (runId && storageAvailable()) sessionStorage.removeItem(TOKEN_PREFIX + runId);
    setTokenAvailable(false);
    setMessage("The local optional-evidence capability was removed from this browser session.");
  }

  if (!active || !runId) return null;

  return <main className="shell" id="mid-evidence-console">
    <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Mid evidence console</p><h2>Measured coverage and review exceptions</h2></div>
        <span className={coverage?.calculated ? "status blue" : "status gray"}>{coverage?.calculated ? `${coverage.percent ?? 0}% coverage` : "coverage pending"}</span>
      </div>
      <p className="muted">Run ID: {runId}. Coverage is based on explicit evidence units, not the maturity score.</p>
      {reviewSummary ? <div className="grid four target-grid">
        <article><b>Verified sections</b><span>{reviewSummary.sections_verified ?? 0}</span></article>
        <article><b>Verified with limits</b><span>{reviewSummary.sections_verified_with_limitations ?? 0}</span></article>
        <article><b>Items requiring review</b><span>{reviewSummary.items_require_review ?? 0}</span></article>
        <article><b>Unsupported claims permitted</b><span>{reviewSummary.unsupported_claims_permitted ?? 0}</span></article>
      </div> : null}
      {coverage?.method ? <p className="warning-box">{coverage.method}</p> : null}
      {coverage?.units?.length ? <details className="help-details"><summary>Coverage units ({coverage.numerator ?? 0}/{coverage.denominator ?? coverage.units.length})</summary>
        <div className="results-grid">{coverage.units.map((unit) => <article className="result-card" key={unit.id}>
          <div className="result-head"><b>{unit.label || unit.id}</b><span className={statusClass(unit.status)}>{unit.status || (unit.available ? "Verified" : "Unavailable")}</span></div>
          {unit.evidence ? <p>{unit.evidence}</p> : null}
          {unit.limitation ? <p className="muted">{unit.limitation}</p> : null}
        </article>)}</div>
      </details> : null}

      <div className="section-head"><div><p className="eyebrow">Review by exception preview</p><h2>Sections not automatically verified</h2></div><span className={exceptions.length ? "status yellow" : "status green"}>{exceptions.length} exceptions</span></div>
      <div className="results-grid">{exceptions.map((section) => <details className="result-card" open key={section.id}>
        <summary><b>{section.label || section.id}</b> <span className={statusClass(section.truth_status)}>{section.truth_status || "Unavailable"}</span></summary>
        <p>{section.summary || "No summary returned."}</p>
        {section.evidence?.length ? <><h3>Evidence</h3><ul className="tight-list">{section.evidence.map((item, index) => <li key={`${section.id}-e-${index}`}>{item}</li>)}</ul></> : null}
        {section.missing_evidence_sources?.length ? <p className="muted">Missing sources: {section.missing_evidence_sources.join(", ")}</p> : null}
        {section.failed_evidence_tools?.length ? <p className="error-box">Failed tools: {section.failed_evidence_tools.join(", ")}</p> : null}
        {section.unavailable?.length ? <ul className="tight-list">{section.unavailable.map((item, index) => <li key={`${section.id}-u-${index}`}>{item}</li>)}</ul> : null}
      </details>)}</div>
      {verified.length ? <details className="help-details"><summary>Verified automatically — evidence available ({verified.length})</summary>
        <div className="results-grid">{verified.map((section) => <article className="result-card" key={section.id}>
          <div className="result-head"><b>{section.label || section.id}</b><span className="status green">Verified</span></div>
          <p>{section.summary || "Direct evidence is available."}</p>
        </article>)}</div>
      </details> : null}
    </section>

    <section className="section panel">
      <details className="help-details">
        <summary>Additional evidence, optional</summary>
        <div className="help-body">
          <p className="warning-box">Submitted context is bound to this Mid run and snapshot. It is not repository proof, cannot change a score automatically, and requires human validation.</p>
          <div className="form-grid">{evidenceFields.map(([key, label]) => <label key={key}>{label}{key === "application_url"
            ? <input value={form[key]} onChange={(event) => setField(key, event.target.value)} placeholder="https://staging.example.com" />
            : <textarea value={form[key]} onChange={(event) => setField(key, event.target.value)} />}</label>)}</div>
          <div className="report-actions">
            <button type="button" className="primary-button" disabled={!API_URL || !tokenAvailable || submitting} onClick={submitEvidence}>{submitting ? "Submitting context..." : "Attach optional evidence"}</button>
            <button type="button" disabled={!tokenAvailable} onClick={forgetCapability}>Forget local capability</button>
          </div>
          {!tokenAvailable ? <p className="muted">The one-time submission capability is not available. A fresh Mid run issues it once after the snapshot is stored.</p> : null}
          {error ? <p className="error-box">{error}</p> : null}
          {message ? <p className="warning-box">{message}</p> : null}
          {optional ? <details className="help-details" open><summary>Optional evidence status</summary>
            <div className="grid four target-grid">
              <article><b>Status</b><span>{optional.status || "not submitted"}</span></article>
              <article><b>Fields attached</b><span>{optional.field_count ?? optional.fields_submitted?.length ?? 0}</span></article>
              <article><b>Verification</b><span>{optional.verification_status || "unavailable"}</span></article>
              <article><b>Automatic score change</b><span>{String(Boolean(optional.score_change_allowed_without_review))}</span></article>
            </div>
            <p className="muted">{optional.retention_note}</p>
          </details> : null}
        </div>
      </details>
    </section>
  </main>;
}
