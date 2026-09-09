type RequestRecord = Record<string, unknown>;

export default function EvidenceRequests({requests, locale, busy, onResolve}: {
  requests: unknown;
  locale: "en" | "es-MX";
  busy: boolean;
  onResolve: (requestId: string) => void;
}) {
  const es = locale === "es-MX";
  const entries = Array.isArray(requests) ? requests.filter((item): item is RequestRecord =>
    !!item && typeof item === "object" && typeof item.request_id === "string" && !!item.request_id.trim()) : [];
  if (!entries.length) return null;
  const text = (value: unknown) => typeof value === "string" ? value : "";
  return <section aria-label={es ? "Solicitudes de evidencia registradas" : "Recorded evidence requests"}>
    <h3>{es ? "Solicitudes de evidencia registradas" : "Recorded evidence requests"}</h3>
    {entries.map((entry) => {
      const id = text(entry.request_id);
      const open = entry.status === "open";
      return <article key={id} style={{overflowWrap: "anywhere", marginBlock: "1rem"}}>
        <h4><code>{id}</code></h4>
        <p>{es ? "Estado" : "Status"}: {open ? (es ? "Abierta" : "Open") : entry.status === "resolved" ? (es ? "Resuelta" : "Resolved") : text(entry.status)}</p>
        <p>{es ? "Candidato" : "Candidate"}: <code>{text(entry.candidate_id)}</code></p>
        <p>{text(entry.request_text)}</p>
        <p>{es ? "Responsable" : "Owner"}: {text(entry.owner)}</p>
        <p>{es ? "Solicitada por" : "Requested by"}: {text(entry.requested_by)} · {text(entry.requested_at)}</p>
        {open ? <button type="button" disabled={busy} onClick={() => onResolve(id)}>{es ? "Resolver solicitud" : "Resolve request"} {id}</button> : null}
        {text(entry.resolution_note) ? <>
          <p>{es ? "Resolución" : "Resolution"}: {text(entry.resolution_note)}</p>
          <p>{es ? "Resuelta por" : "Resolved by"}: {text(entry.resolved_by)} · {text(entry.resolved_at)}</p>
          <ul>{Array.isArray(entry.evidence_references) ? entry.evidence_references.filter((ref): ref is string => typeof ref === "string").map((ref, index) => <li key={index}>{ref}</li>) : null}</ul>
        </> : null}
      </article>;
    })}
  </section>;
}
