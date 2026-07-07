"use client";

import {useEffect, useMemo, useState} from "react";

type JobType = "quick" | "client" | "repair" | "retainer";
type FormState = {jobType: JobType; repository: string; clientName: string; projectName: string; authorizedBy: string; authorizationScope: string; notes: string; savedAt?: string};

const STORAGE_KEY = "nico.startJobWizard.v1";
const jobOptions: Array<{id: JobType; title: string; bestFor: string; path: string[]}> = [
  {id: "quick", title: "Quick repo health check", bestFor: "Fast internal read-only assessment.", path: ["Confirm authorization", "Run Express", "Review unavailable evidence", "Download PDF"]},
  {id: "client", title: "Client Express assessment", bestFor: "Paid technical audit package.", path: ["Confirm scope", "Run Scanner Worker", "Run Express", "Build client package", "Export and sign off"]},
  {id: "repair", title: "Repair failed check", bestFor: "Fixing CI, scanner, report, dependency, or UX failures.", path: ["Paste exact issue", "Add evidence", "Generate repair suggestion", "Open approval", "Create draft PR"]},
  {id: "retainer", title: "Retainer project", bestFor: "Weekly operating report and ongoing support.", path: ["Add weekly evidence", "Run Retainer Ops", "Review approvals", "Export status report"]},
];

const defaults: FormState = {
  jobType: "client",
  repository: "BoneManTGRM/NICO",
  clientName: "NICO",
  projectName: "NICO",
  authorizedBy: "",
  authorizationScope: "Defensive technical assessment of my own authorized repository for report accuracy, scanner evidence, CI/CD maturity, production readiness, and client-ready reporting.",
  notes: "",
};

function loadSaved(): FormState {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? {...defaults, ...JSON.parse(raw)} : defaults;
  } catch {
    return defaults;
  }
}

export default function StartJobPage() {
  const [form, setForm] = useState<FormState>(defaults);
  const [saved, setSaved] = useState(false);

  useEffect(() => { setForm(loadSaved()); }, []);

  const selected = useMemo(() => jobOptions.find((item) => item.id === form.jobType) || jobOptions[1], [form.jobType]);
  const readyCount = [form.repository, form.clientName, form.projectName, form.authorizedBy, form.authorizationScope].filter((item) => item.trim()).length;
  const ready = readyCount === 5;
  const commandCenterLink = `/?repository=${encodeURIComponent(form.repository)}&client=${encodeURIComponent(form.clientName)}&project=${encodeURIComponent(form.projectName)}`;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) { setForm((current) => ({...current, [key]: value})); setSaved(false); }
  function saveJob() { const payload = {...form, savedAt: new Date().toISOString()}; window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload)); setForm(payload); setSaved(true); }
  function resetJob() { window.localStorage.removeItem(STORAGE_KEY); setForm(defaults); setSaved(false); }
  async function copyScope() { await navigator.clipboard?.writeText(form.authorizationScope); setSaved(true); }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Start Job Wizard</p>
        <h1>Start a job</h1>
        <p className="lead">Choose the job type, capture authorization, save the scope, then move into the correct NICO workflow.</p>
        <div className="hero-actions"><a className="primary-link" href={commandCenterLink}>Open command center</a><a className="secondary-link" href="/easy">Easy Mode</a><a className="secondary-link" href="/scanner-workflow">Scanner to Express</a><a className="secondary-link" href="/guided-workflow">Guided workflow</a></div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Step 1</p><h2>Choose job type</h2></div><span className="status blue">{selected.title}</span></div>
        <div className="results-grid">
          {jobOptions.map((job) => <button type="button" className="result-card" key={job.id} onClick={() => update("jobType", job.id)} aria-pressed={form.jobType === job.id}><div className="result-head"><b>{job.title}</b><span className={form.jobType === job.id ? "status green" : "status gray"}>{form.jobType === job.id ? "selected" : "choose"}</span></div><p>{job.bestFor}</p></button>)}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Step 2</p><h2>Scope and authorization</h2></div><span className={ready ? "status green" : "status yellow"}>{readyCount}/5 ready</span></div>
        <p className="warning-box">Use only for systems you own or have explicit permission to assess. Saving the job does not run scanners or change code.</p>
        <div className="form-grid">
          <label>Repository owner/name<input value={form.repository} onChange={(event) => update("repository", event.target.value)} placeholder="owner/repo" /></label>
          <label>Client name<input value={form.clientName} onChange={(event) => update("clientName", event.target.value)} placeholder="Client" /></label>
          <label>Project name<input value={form.projectName} onChange={(event) => update("projectName", event.target.value)} placeholder="Project" /></label>
          <label>Authorized by<input value={form.authorizedBy} onChange={(event) => update("authorizedBy", event.target.value)} placeholder="Name or role" /></label>
        </div>
        <label className="wide-label">Authorization scope<textarea value={form.authorizationScope} onChange={(event) => update("authorizationScope", event.target.value)} /></label>
        <label className="wide-label">Job notes<textarea value={form.notes} onChange={(event) => update("notes", event.target.value)} placeholder="Optional notes, client constraints, evidence reminders, or blockers." /></label>
        <div className="report-actions"><button type="button" className="primary-button" onClick={saveJob}>Save job</button><button type="button" onClick={copyScope}>Copy scope</button><button type="button" onClick={resetJob}>Reset</button>{saved ? <span className="muted">Saved locally{form.savedAt ? ` at ${form.savedAt}` : ""}</span> : null}</div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Step 3</p><h2>Next actions</h2></div><span className={ready ? "status green" : "status yellow"}>{ready ? "ready" : "needs scope"}</span></div>
        <div className="results-grid">
          {selected.path.map((item, index) => <article className="result-card" key={item}><div className="result-head"><b>{index + 1}. {item}</b><span className="status gray">next</span></div><p>{index === 0 ? "Complete this before moving forward." : "Continue only after the prior step is reviewed."}</p></article>)}
        </div>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Recommended route</p><p>{form.jobType === "client" ? "Run Scanner Worker first, then Express, then client package/export." : form.jobType === "repair" ? "Use Repair Intelligence with exact failure evidence and affected files." : form.jobType === "retainer" ? "Use Retainer Ops with weekly evidence and blockers." : "Run Express and review the PDF before taking action."}</p></div>
          <div className="mini-panel"><p className="eyebrow">Client-ready rule</p><p>Do not call the job final until authorization, unavailable evidence, findings, report wording, and any code changes are reviewed by a human.</p></div>
        </div>
      </section>
    </main>
  );
}
