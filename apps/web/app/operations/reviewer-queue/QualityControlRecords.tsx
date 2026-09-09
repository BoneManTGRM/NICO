type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const text = (value: unknown) => typeof value === "string" ? value : "";
const reasons: Record<string, [string, string]> = {
  quality_control_missing: ["QC has not been recorded", "No se ha registrado control de calidad"],
  candidate_disposition_incomplete: ["Complete the candidate review first", "Complete primero la revisión del candidato"],
  quality_control_disagreement: ["QC disagrees; resolve the disagreement and repeat QC", "El control de calidad discrepa; resuelva la discrepancia y repita el control"],
  independent_quality_control_required: ["A different reviewer must perform QC", "Otro revisor debe realizar el control de calidad"],
  quality_control_disposition_binding_missing: ["Repeat QC to bind it to the exact reviewer decision", "Repita el control de calidad para vincularlo con la decisión exacta"],
  quality_control_disposition_changed: ["The reviewer decision changed; repeat QC", "La decisión del revisor cambió; repita el control de calidad"],
};

export default function QualityControlRecords({records, blockers, events, locale, busy, onSelect}: {
  records: unknown; blockers: unknown; events: unknown; locale: "en" | "es-MX";
  busy: boolean; onSelect: (candidateId: string) => void;
}) {
  const es = locale === "es-MX";
  const current = record(records), pending = record(blockers);
  const ids = [...new Set([...Object.keys(current), ...Object.keys(pending)])].sort();
  if (!ids.length) return null;
  const history = Array.isArray(events) ? events.map(record).filter(item => item.action === "quality_control") : [];
  const outcome = (value: unknown) => value === "agree" ? (es ? "De acuerdo" : "Agree") : value === "disagree" ? (es ? "En desacuerdo" : "Disagree") : (es ? "Pendiente" : "Pending");
  return <section aria-label={es ? "Control de calidad registrado" : "Recorded quality control"}>
    <h3>{es ? "Control de calidad registrado" : "Recorded quality control"}</h3>
    {ids.map(id => {
      const entry = record(current[id]);
      const reason = text(pending[id]);
      return <article key={id} style={{overflowWrap: "anywhere", marginBlock: "1rem"}}>
        <h4><code>{id}</code></h4>
        <p>{outcome(entry.qc_outcome)} · {text(entry.reviewer)} · {text(entry.reviewed_at)}</p>
        <p>{text(entry.qc_note)}</p>
        {reason ? <>
          <p>{reasons[reason]?.[es ? 1 : 0] || (es ? "Se requiere control de calidad" : "QC required")}</p>
          <button type="button" disabled={busy} onClick={() => onSelect(id)}>{es ? "Revisar control de calidad" : "Review QC"} {id}</button>
        </> : null}
      </article>;
    })}
    {history.length ? <details><summary>{es ? "Historial de control de calidad" : "QC history"}</summary>
      {history.map((event, index) => {const payload = record(event.payload); return <article key={index} style={{overflowWrap: "anywhere"}}>
        <p><code>{text(payload.candidate_id)}</code> · {outcome(payload.qc_outcome)} · {text(event.reviewer)} · {text(event.recorded_at)}</p>
        <p>{text(payload.qc_note)}</p>
      </article>;})}
    </details> : null}
  </section>;
}
