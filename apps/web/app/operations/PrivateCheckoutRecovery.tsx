"use client";

import {useState} from "react";

type Diagnosis = {run_id: string; scan_id: string; commit_sha: string; failure_fingerprint: string; retry_allowed: boolean};

export default function PrivateCheckoutRecovery({runId, spanish, returnPath}: {runId: string; spanish: boolean; returnPath: string}) {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const tr = (en: string, es: string) => spanish ? es : en;
  async function request(retry: boolean) {
    if (busy || (retry && !diagnosis?.retry_allowed)) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/scanner-checkout-recovery`, {
        method: retry ? "POST" : "GET", credentials: "same-origin", cache: "no-store",
        ...(retry ? {headers: {"Content-Type": "application/json"}, body: JSON.stringify({
          scan_id: diagnosis!.scan_id, commit_sha: diagnosis!.commit_sha,
          failure_fingerprint: diagnosis!.failure_fingerprint,
        })} : {}),
      });
      if (!response.ok) {
        setDiagnosis(null);
        setMessage(response.status === 401 || response.status === 403
          ? tr("An existing owner administrator session is required for this recovery.", "Esta recuperación requiere una sesión existente de administrador propietario.")
          : tr("This checkout cannot be retried safely. The preserved failure remains authoritative.", "No se puede reintentar esta descarga de forma segura. El fallo conservado sigue siendo autoritativo."));
        return;
      }
      const value = await response.json();
      if (value.run_id !== runId || !/^scan_snapshot_[A-Za-z0-9_]+$/.test(value.scan_id || "")
          || !/^[a-f0-9]{40}$/.test(value.commit_sha || "") || !/^[a-f0-9]{64}$/.test(value.failure_fingerprint || "")) {
        throw new Error("identity");
      }
      if (retry && response.status === 202 && value.same_run_and_scan_preserved === true) {
        const target = new URL(returnPath, window.location.origin);
        target.searchParams.set("tier", "comprehensive");
        target.searchParams.set("run_id", runId);
        window.location.assign(`${target.pathname}${target.search}`);
        return;
      }
      setDiagnosis(value);
      if (!value.retry_allowed) setMessage(tr("The checkout is not eligible for this one-time recovery.", "La descarga no cumple los requisitos de esta recuperación de un solo intento."));
    } catch {
      setDiagnosis(null);
      setMessage(tr("Recovery could not be verified. Reload the exact run before taking further action.", "No se pudo verificar la recuperación. Vuelva a cargar la ejecución exacta antes de continuar."));
    } finally {
      setBusy(false);
    }
  }
  return <section>
    <h3>{tr("Private scanner checkout recovery", "Recuperación de descarga privada para analizadores")}</h3>
    <p>{tr("Owner administrators can retry the repaired private checkout once, only if no scanner ran. The same assessment and scan IDs and the original failure are retained. This does not approve or authorize delivery.", "Los administradores propietarios pueden reintentar una vez la descarga privada reparada, solo si no se ejecutó ningún analizador. Se conservan los mismos ID de evaluación y análisis y el fallo original. Esto no aprueba ni autoriza la entrega.")}</p>
    <button type="button" disabled={busy} onClick={() => void request(false)}>{tr("Inspect private scanner checkout", "Inspeccionar descarga privada para analizadores")}</button>
    {diagnosis?.retry_allowed ? <>
      <p><code>{diagnosis.scan_id}</code> · <code>{diagnosis.commit_sha}</code></p>
      <button type="button" disabled={busy} onClick={() => void request(true)}>{tr("Retry this private checkout once", "Reintentar esta descarga privada una vez")}</button>
    </> : null}
    {message ? <p role="status">{message}</p> : null}
  </section>;
}
