"use client";

import {FormEvent, useEffect, useState} from "react";
import {localePreservingHref} from "../../assessment/assessmentLocale";

type ScannerRecord = {
  scanner_name: string;
  execution_status: string;
  scanner_version?: string | null;
  configuration?: {generated_config_sha256?: string | null; full_configuration_verified: boolean};
  raw_artifact: {availability: string; sha256?: string | null; gzip_sha256?: string | null};
};
type Inventory = {
  artifact_schema: string;
  run_id: string;
  repository: string;
  commit_sha: string;
  run_revision: number | null;
  checked_at: string;
  status: "inventory_complete" | "inventory_incomplete";
  read_only: true;
  scanner_records: ScannerRecord[];
};

export default function ScannerEvidencePage() {
  const [runId, setRunId] = useState("");
  const [password, setPassword] = useState("");
  const [spanish, setSpanish] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const tr = (en: string, es: string) => spanish ? es : en;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRunId(params.get("run_id") || "");
    const locale = (params.get("lang") ?? params.get("language") ?? "").toLowerCase();
    setSpanish(locale === "es-mx" || locale === "es");
  }, []);

  function switchLanguage() {
    const url = new URL(window.location.href);
    // Keep the current recovery identity and retire the legacy locale alias.
    if (runId.trim()) url.searchParams.set("run_id", runId.trim());
    url.searchParams.delete("language");
    window.location.assign(localePreservingHref(
      url.pathname, url.search, url.hash, spanish ? "en-US" : "es-MX",
    ));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || !/^comprun_[A-Za-z0-9_-]{1,120}$/.test(runId.trim())) return;
    setLoading(true);
    setError("");
    setInventory(null);
    try {
      if (password) {
        // Use the established credential exchange. The owner credential never
        // enters an evidence request, URL, browser storage or rendered output.
        const login = await fetch("/api/nico/operator-session", {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({password}),
          cache: "no-store",
        });
        setPassword("");
        if (!login.ok) {
          setError(tr("Owner sign-in could not be completed.", "No se pudo completar el inicio de sesión del propietario."));
          return;
        }
      }
      const response = await fetch(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/scanner-evidence`, {
        method: "GET", credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) {
        setError(response.status === 401 || response.status === 403
          ? tr("An existing NICO owner administrator account is required. A scoped specialist or production-proof identity cannot access this inventory.", "Se requiere una cuenta existente de administrador propietario de NICO. Una identidad de especialista con alcance limitado o de prueba de producción no puede acceder a este inventario.")
          : tr("The bound scanner inventory is unavailable or its source identity could not be verified. The assessment has not been changed.", "El inventario vinculado de analizadores no está disponible o no se pudo verificar su identidad de origen. La evaluación no se ha modificado."));
        return;
      }
      const value = await response.json() as Inventory;
      if (value.artifact_schema !== "nico.comprehensive-scanner-inventory.v1" || value.run_id !== runId.trim() || value.read_only !== true || !Array.isArray(value.scanner_records)) {
        setError(tr("The inventory response could not be verified.", "No se pudo verificar la respuesta del inventario."));
        return;
      }
      setInventory(value);
      const url = new URL(window.location.href);
      url.searchParams.set("run_id", value.run_id);
      window.history.replaceState(null, "", url);
    } catch {
      setError(tr("The inventory request did not complete. Retry this read when the connection is available.", "La consulta del inventario no se completó. Reintente esta lectura cuando la conexión esté disponible."));
    } finally {
      setPassword("");
      setLoading(false);
    }
  }

  return <main className="shell" lang={spanish ? "es-MX" : "en"}>
    <section className="hero-card">
      <p className="eyebrow">NICO COMPREHENSIVE</p>
      <h1>{tr("Retained scanner evidence", "Evidencia conservada de los analizadores")}</h1>
      <p>{tr("Owner administrators can inspect metadata and verify that the retained scanner bytes still match their recorded checksums. Missing or mismatched evidence remains explicit.", "Los administradores propietarios pueden consultar metadatos y verificar que los bytes conservados de los analizadores coincidan con sus sumas de verificación registradas. La evidencia faltante o que no coincide permanece explícita.")}</p>
      <p>{tr("This read does not evaluate coverage, resolve findings, rebuild the assessment, approve a report or authorize delivery.", "Esta lectura no evalúa la cobertura, resuelve hallazgos, reconstruye la evaluación, aprueba informes ni autoriza la entrega.")}</p>
      <button type="button" onClick={switchLanguage}>{spanish ? "English" : "Español (México)"}</button>
      <form onSubmit={submit} className="result-card">
        <label htmlFor="scanner-evidence-run"><b>{tr("Saved assessment run ID", "ID de la evaluación guardada")}</b></label>
        <input id="scanner-evidence-run" disabled={loading} value={runId} onChange={event => {setRunId(event.target.value); setInventory(null);}} required pattern="comprun_[A-Za-z0-9_-]{1,120}" maxLength={128} autoComplete="off" />
        <label htmlFor="scanner-evidence-owner-password"><b>{tr("Owner administrator password (optional)", "Contraseña del administrador propietario (opcional)")}</b></label>
        <input id="scanner-evidence-owner-password" disabled={loading} type="password" value={password} onChange={event => setPassword(event.target.value)} maxLength={4096} autoComplete="current-password" aria-describedby="scanner-evidence-session-help" />
        <p id="scanner-evidence-session-help" className="muted">{tr("Leave blank to use your current owner session. Enter your existing owner password only to sign in again; scoped credentials are not promoted.", "Deje este campo vacío para usar su sesión actual de propietario. Ingrese su contraseña existente de propietario solo para iniciar sesión nuevamente; las credenciales de alcance limitado no reciben permisos adicionales.")}</p>
        <button type="submit" disabled={loading || !runId.trim()}>{loading ? tr("Checking retained evidence…", "Verificando evidencia conservada…") : tr("Load scanner evidence inventory", "Cargar inventario de evidencia de analizadores")}</button>
        {error ? <p role="alert">{error}</p> : null}
      </form>
      {inventory ? <section aria-live="polite" data-nico-scanner-evidence="true">
        <h2>{tr("Recorded inventory", "Inventario registrado")}</h2>
        <p>{inventory.repository} · <code>{inventory.commit_sha}</code></p>
        <p>{inventory.run_id} · {tr("Revision", "Revisión")} {inventory.run_revision ?? tr("unknown", "desconocida")} · {inventory.checked_at}</p>
        <p>{inventory.status === "inventory_complete"
          ? tr("All listed retained byte checks passed. Scanner coverage and specialist qualification remain separate.", "Todas las verificaciones de bytes conservados enumeradas se aprobaron. La cobertura de los analizadores y la habilitación para especialistas se evalúan por separado.")
          : tr("The inventory is incomplete. Review the explicit availability states below.", "El inventario está incompleto. Revise los estados explícitos de disponibilidad a continuación.")}</p>
        <div style={{overflowX: "auto"}}><table>
          <caption>{tr("Scanner execution declarations and current retained-byte availability", "Declaraciones de ejecución y disponibilidad actual de los bytes conservados")}</caption>
          <thead><tr>{[tr("Scanner", "Analizador"), tr("Recorded state", "Estado registrado"), tr("Version", "Versión"), tr("Retained bytes", "Bytes conservados")].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{inventory.scanner_records.map((record, index) => <tr key={`${record.scanner_name}-${index}`}><th scope="row">{record.scanner_name}</th><td>{record.execution_status}</td><td>{record.scanner_version ?? tr("Unavailable", "No disponible")}</td><td>{record.raw_artifact.availability}</td></tr>)}</tbody>
        </table></div>
        <details><summary>{tr("Checksum and evidence metadata", "Metadatos de evidencia y sumas de verificación")}</summary><pre style={{whiteSpace: "pre-wrap", overflowWrap: "anywhere"}}>{JSON.stringify(inventory, null, 2)}</pre></details>
      </section> : null}
    </section>
  </main>;
}
