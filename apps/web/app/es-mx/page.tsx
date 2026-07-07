"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

const safetyRules = ["Solo uso defensivo", "Solo sistemas autorizados", "Sin explotación", "Sin fuerza bruta", "Sin bypass de autenticación", "Sin robo de credenciales", "Sin acciones destructivas"];
const assessmentAreas = ["Auditoría de código", "Dependencias y ecosistema de librerías", "Revisión de secretos", "Análisis estático", "CI/CD", "Arquitectura y deuda técnica", "Velocidad y complejidad", "Reportes Markdown / HTML / PDF"];

type Health = {status?: string; system?: string; mode?: string};
type Section = {id: string; label: string; score: number; status: string; status_label?: string; summary: string; evidence: string[]; findings?: string[]; unavailable?: string[]};
type AssessmentResult = {status?: string; repository?: string; generated_at?: string; executive_summary?: string; report_language?: string; language_label?: string; maturity_signal?: {level?: string; score?: number; summary?: string}; sections?: Section[]; findings?: string[]; repairs?: string[]; reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string}; human_review_required?: boolean};

function statusClass(status?: string) {
  if (status === "green" || status === "passed" || status === "approved" || status === "complete") return "status green";
  if (status === "yellow" || status === "pending" || status === "running" || status === "queued") return "status yellow";
  if (status === "red" || status === "failed" || status === "error" || status === "rejected" || status === "timeout") return "status red";
  return "status gray";
}

function statusText(status?: string, label?: string) {
  if (label) return label;
  if (status === "green") return "verde";
  if (status === "yellow") return "amarillo";
  if (status === "red") return "rojo";
  if (status === "gray") return "gris";
  if (status === "complete") return "completo";
  return status || "sin estado";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">Todavía no hay evidencia.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export default function Page() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  const [assessmentError, setAssessmentError] = useState("");
  const [copied, setCopied] = useState("");

  const backendConfigured = Boolean(API_URL);
  const backendOnline = health?.status === "ok";

  async function checkBackend() {
    if (!backendConfigured) { setHealthError("No está configurada la variable NEXT_PUBLIC_NICO_API_URL para este despliegue."); return; }
    setHealthError("");
    try {
      const response = await fetch(`${API_URL}/health`, {cache: "no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(`Falló el health check con ${response.status}`);
      setHealth(data);
    } catch (error) {
      setHealth(null);
      setHealthError(error instanceof Error ? error.message : "Falló la revisión del backend");
    }
  }

  useEffect(() => { checkBackend(); }, []);

  async function runHostedAssessment() {
    if (!backendConfigured) { setAssessmentError("La URL del backend no está configurada en Vercel."); return; }
    setAssessmentError(""); setCopied(""); setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/github`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({repository, authorized, client_name: clientName, project_name: projectName, assessment_mode: "express_es_mx", timeframe_days: 180})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Falló la evaluación con ${response.status}`);
      setAssessment(data);
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Falló la evaluación");
    } finally {
      setLoading(false);
    }
  }

  async function copyReport(kind: "markdown" | "html") {
    const text = assessment?.reports?.[kind];
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setCopied(`Reporte ${kind.toUpperCase()} copiado`);
  }

  function downloadPdf() {
    const encoded = assessment?.reports?.pdf_base64;
    if (!encoded) return;
    const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], {type: "application/pdf"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = assessment?.reports?.pdf_filename || "nico-evaluacion-es-mx.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Command Center</p>
        <h1>Evaluación técnica en Español de México</h1>
        <p className="lead">NICO genera evaluaciones defensivas y reportes basados en evidencia. La evidencia faltante se muestra claramente y nunca se trata como verificada.</p>
        <div className="hero-actions">
          <a href="/" className="secondary-link">English</a>
          <a href="/es-mx" className="primary-link">Español (México)</a>
          <a href="#hosted" className="secondary-link">Correr Express</a>
          <a href="#safety" className="secondary-link">Reglas de uso</a>
        </div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Estado del sistema</p><h2>Frontend / backend Railway</h2></div><span className={backendOnline ? "status green" : backendConfigured ? "status yellow" : "status red"}>{backendOnline ? "Backend en línea" : backendConfigured ? "Backend configurado" : "Backend faltante"}</span></div>
        <div className="grid three"><article><b>Frontend</b><span>https://app.nicoaudit.com/es-mx</span></article><article><b>Backend URL</b><span>{API_URL || "No configurado"}</span></article><article><b>Health</b><span>{health?.status || healthError || "Revisando"}</span></article></div>
        <button type="button" className="small-button" onClick={checkBackend}>Revisar backend</button>
        {healthError ? <p className="error-box">{healthError}</p> : null}
      </section>

      <section id="hosted" className="section panel">
        <div className="section-head"><div><p className="eyebrow">Evaluación Express</p><h2>Evaluar un repositorio autorizado de GitHub</h2></div><span className="status gray">90–95%</span></div>
        <p className="warning-box">Solo evalúa repositorios que sean tuyos o que tengas permiso explícito para revisar. NICO hace evaluación defensiva de solo lectura y no realiza acciones destructivas.</p>
        <div className="form-grid"><label>Repositorio owner/name o URL de GitHub<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label><label>Cliente, opcional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Nombre del cliente" /></label><label>Proyecto, opcional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Nombre del proyecto" /></label></div>
        <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />Confirmo que soy dueño de este objetivo o tengo permiso explícito para evaluarlo.</label>
        <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runHostedAssessment}>{loading ? "Corriendo..." : "Correr evaluación Express en español"}</button>
        {assessmentError ? <p className="error-box">{assessmentError}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Resultado Express</p><h2>{assessment?.maturity_signal?.level ? `${assessment.maturity_signal.level}` : "Esperando evaluación"}</h2></div><span className={assessment?.maturity_signal?.level ? "status blue" : "status gray"}>{assessment?.language_label || "Español (México)"}</span></div>
        {assessment?.human_review_required ? <p className="warning-box">Se requiere revisión humana antes de entregar esto a cliente.</p> : null}
        {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
        <div className="results-grid">{assessment?.sections?.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{statusText(item.status, item.status_label)} · {item.score}/100</span></div><p>{item.summary}</p><h3>Evidencia</h3><ListBlock items={item.evidence} />{item.findings?.length ? <><h3>Hallazgos</h3><ListBlock items={item.findings} /></> : null}{item.unavailable?.length ? <><h3>Datos no disponibles</h3><ListBlock items={item.unavailable} /></> : null}</article>)}</div>
        <div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Hallazgos</p><ListBlock items={assessment?.findings} /></div><div className="mini-panel"><p className="eyebrow">Reparaciones</p><ListBlock items={assessment?.repairs} /></div></div>
        <div className="report-actions"><button type="button" disabled={!assessment?.reports?.markdown} onClick={() => copyReport("markdown")}>Copiar Markdown</button><button type="button" disabled={!assessment?.reports?.html} onClick={() => copyReport("html")}>Copiar HTML</button><button type="button" disabled={!assessment?.reports?.pdf_base64} onClick={downloadPdf}>Descargar PDF</button>{copied ? <span className="muted">{copied}</span> : null}</div>
      </section>

      <section className="section panel"><div className="section-head"><div><p className="eyebrow">Alcance de evaluación</p><h2>Checks basados en evidencia</h2></div><span className="status gray">Sin datos falsos</span></div><div className="scope-grid">{assessmentAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}</div></section>

      <section id="safety" className="section two-col"><div className="panel"><p className="eyebrow">Límite de seguridad</p><h2>Uso permitido</h2><ul className="tight-list">{safetyRules.map((rule) => <li key={rule}>{rule}</li>)}</ul></div><div className="panel"><p className="eyebrow">Revisión humana</p><h2>Obligatoria para entrega a cliente</h2><ul className="tight-list"><li>Validar hechos y evidencia antes de entregar.</li><li>Confirmar contexto del cliente y stakeholders.</li><li>Aprobar cambios que impacten producción.</li><li>Revisar roadmap y recomendaciones de recursos.</li></ul></div></section>
    </main>
  );
}
