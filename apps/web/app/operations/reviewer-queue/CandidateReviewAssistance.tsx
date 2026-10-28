"use client";

import {useState} from "react";

type Packet = {
  candidate_id: string;
  record_index: number;
  recommendation: string;
  limitations: string[];
  source_url: string | null;
  input_sha256: string;
  existing_review_profile_cluster_id: string;
};
export type Assistance = {
  artifact_schema: string;
  pending_record_count: number;
  queue: Packet[];
};

const recommendations: Record<string, [string, string]> = {
  individual_material_review: ["Prioritize individual risk review", "Priorizar revisión individual del riesgo"],
  resolve_evidence_gaps: ["Resolve evidence gaps before disposition", "Resolver brechas de evidencia antes de decidir"],
  review_nonblocking_proposal: ["Review retained nonblocking proposal", "Revisar propuesta conservada de no bloqueo"],
};
const limitations: Record<string, [string, string]> = {
  existing_individual_review_required: ["Existing controls require individual review", "Los controles existentes requieren revisión individual"],
  duplicate_candidate_identity: ["Candidate identity is missing or duplicated", "Falta la identidad del candidato o está duplicada"],
  source_identity_or_location_unverified: ["Exact source link unavailable", "Enlace al código exacto no disponible"],
  exact_source_evidence_missing: ["Exact source evidence missing", "Falta evidencia del código exacto"],
  ambiguous_context: ["Ambiguous evidence binding", "Vinculación de evidencia ambigua"],
  evidence_changed: ["Evidence changed; revalidation needed", "La evidencia cambió; requiere revalidación"],
  analysis_not_current_deterministic: ["Current deterministic analysis not established", "No se estableció un análisis determinista actual"],
  analysis_unavailable: ["Analysis failed or is unavailable", "El análisis falló o no está disponible"],
  supporting_evidence_missing: ["Supporting evidence missing", "Falta evidencia de respaldo"],
  unresolved_proof_gaps: ["Unresolved proof gaps", "Brechas de prueba sin resolver"],
  counterevidence_requires_review: ["Counterevidence needs review", "La contraevidencia requiere revisión"],
  high_impact_individual_review: ["High-impact or secret candidate needs individual review", "El candidato de alto impacto o secreto requiere revisión individual"],
  confidence_insufficient_for_nonblocking_proposal: ["Confidence does not support a nonblocking proposal", "La confianza no respalda una propuesta de no bloqueo"],
};

export default function CandidateReviewAssistance({value, locale}: {value: Assistance; locale: "en" | "es-MX"}) {
  const [page, setPage] = useState(0);
  const es = locale === "es-MX";
  const language = es ? 1 : 0;
  const pages = Math.max(1, Math.ceil(value.queue.length / 25));
  const current = Math.min(page, pages - 1);
  return <section aria-label={es ? "Asistencia para revisión" : "Review assistance"}>
    <h3>{es ? "Cola priorizada de revisión asistida" : "Prioritized assisted-review queue"}</h3>
    <p>{es ? "Análisis determinista conservado; no se realizó una nueva investigación del código ni se consultó un modelo. Los enlaces son ubicaciones, no prueba de inspección. Cada disposición sigue siendo humana." : "Retained deterministic analysis; no new source investigation or model call was performed. Links are locators, not proof of inspection. Every disposition remains human."}</p>
    <p>{value.pending_record_count} {es ? "registros pendientes. Los grupos comparten un perfil de revisión; no demuestran equivalencia ni permiten descartar candidatos." : "pending records. Groups share a review profile; they do not establish equivalence or permit candidate dismissal."}</p>
    <ol start={current * 25 + 1}>
      {value.queue.slice(current * 25, current * 25 + 25).map(packet => <li key={`${packet.record_index}:${packet.candidate_id}`}>
        <details data-review-assistance-candidate={packet.candidate_id}>
          <summary><code>{packet.candidate_id}</code> — {(recommendations[packet.recommendation] ?? recommendations.resolve_evidence_gaps)[language]}</summary>
          {packet.source_url && /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/blob\/[0-9a-f]{40}\//.test(packet.source_url) ? <p><a href={packet.source_url} target="_blank" rel="noopener noreferrer">{es ? "Abrir ubicación del código exacto" : "Open exact source location"}</a></p> : null}
          <ul>{packet.limitations.map(code => <li key={code}>{(limitations[code] ?? ["Additional evidence review required", "Se requiere revisión adicional de evidencia"])[language]}</li>)}</ul>
          <p>{es ? "Grupo de revisión existente" : "Existing review group"}: <code>{packet.existing_review_profile_cluster_id || "—"}</code></p>
          <p>{es ? "Huella de los datos de entrada" : "Input fingerprint"}: <code>{packet.input_sha256}</code></p>
        </details>
      </li>)}
    </ol>
    <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>{es ? "Anterior" : "Previous"}</button>
    <span> {current + 1} / {pages} </span>
    <button type="button" disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>{es ? "Siguiente" : "Next"}</button>
  </section>;
}
