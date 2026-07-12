"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const RUN_KEY = "nico.mid.active_run";
const TOKEN_PREFIX = "nico.mid.evidence_token.";

function packetPayload() {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return {
    application_url: origin.startsWith("http") ? origin : undefined,
    architecture_documents: "Version-controlled architecture and deployment context: docs/mid-evidence/ARCHITECTURE.md and docs/mid-evidence/DEPLOYMENT.md. These describe the intended design and configured deployment boundaries and require human validation.",
    product_requirements: "Version-controlled product and QA context: docs/mid-evidence/PRODUCT_CONTEXT.md and docs/mid-evidence/QA.md. These describe intended behavior and verification boundaries, not proof that every runtime path is correct.",
    existing_roadmap: "Version-controlled remediation and acceptance roadmap: docs/mid-evidence/ROADMAP.md. Completion still requires a fresh snapshot-bound Mid run and human review.",
    business_priorities: "Documented priorities: authorized defensive use, complete evidence collection, truthful unavailable and failed states, no unsupported clean claims, human approval before delivery, and mobile-readable reports. Sources: docs/mid-evidence/PRODUCT_CONTEXT.md and docs/mid-evidence/ROADMAP.md.",
  };
}

export default function MidEvidencePacketHelper() {
  const [active, setActive] = useState(false);
  const [runId, setRunId] = useState("");
  const [tokenAvailable, setTokenAvailable] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (window.location.pathname !== "/") return;
    setActive(true);
    const syncSession = () => {
      try {
        const storedRun = sessionStorage.getItem(RUN_KEY) || "";
        setRunId(storedRun.startsWith("midrun_") ? storedRun : "");
        setTokenAvailable(Boolean(storedRun && sessionStorage.getItem(TOKEN_PREFIX + storedRun)));
      } catch {
        setRunId("");
        setTokenAvailable(false);
      }
    };
    syncSession();
    const timer = window.setInterval(syncSession, 1000);
    window.addEventListener("focus", syncSession);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", syncSession);
    };
  }, []);

  async function attachPacket() {
    if (!API_URL || !runId || submitting) return;
    setError("");
    setMessage("");
    let token = "";
    try {
      token = sessionStorage.getItem(TOKEN_PREFIX + runId) || "";
    } catch {
      token = "";
    }
    if (!token) {
      setTokenAvailable(false);
      setError("The optional-evidence capability is not available in this browser session. Start a fresh Mid run to issue a new capability.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId)}/evidence`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token, ...packetPayload()}),
        cache: "no-store",
        referrerPolicy: "no-referrer",
      });
      const data = await response.json();
      if (!response.ok || data?.status !== "submitted") {
        throw new Error(data?.detail?.message || data?.error || "The evidence packet could not be attached.");
      }
      setMessage("The version-controlled NICO evidence packet was attached to this exact Mid run. It remains human-review-bound and does not change scores automatically.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The evidence packet could not be attached.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!active || !runId) return null;

  return <section className="section panel" id="mid-evidence-packet-helper">
    <div className="section-head">
      <div><p className="eyebrow">Mid completion actions</p><h2>Finish the evidence and review chain</h2></div>
      <span className={tokenAvailable ? "status blue" : "status gray"}>{tokenAvailable ? "evidence capability available" : "fresh run required"}</span>
    </div>
    <p className="muted">Active run: {runId}. Repository context can be attached as human-review evidence; it is never converted into automatic repository proof.</p>
    <div className="report-actions">
      <button type="button" className="primary-button" disabled={!API_URL || !tokenAvailable || submitting} onClick={attachPacket}>{submitting ? "Attaching evidence packet..." : "Attach NICO evidence packet"}</button>
      <a className="secondary-link" href="/">Start a fresh Mid run</a>
      <a className="secondary-link" href="/mid-review">Review exceptions</a>
      <a className="secondary-link" href="/mid-report">Generate Mid draft</a>
    </div>
    {error ? <p className="error-box">{error}</p> : null}
    {message ? <p className="summary-box">{message}</p> : null}
    <p className="muted">Native iOS and Android parity remains unavailable until real builds or access instructions are supplied. Stakeholder conclusions still require actual stakeholder evidence.</p>
  </section>;
}
