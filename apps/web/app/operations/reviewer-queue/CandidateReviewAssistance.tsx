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
  source_investigation?: {available: boolean; candidate_count?: number; completed_count?: number; source_availability_counts?: Record<string, number>;
    packets: {candidate_id: string; rule_id: string; completed: boolean; source_sha256?: string; source_path?: string; line?: number; reason: string; source_availability_detail?: string}[]};
};

const investigationReasons: Record<string, [string, string]> = {
  source_scope_unavailable_or_stale: ["Source scope missing or stale", "Alcance del código ausente u obsoleto"],
  investigation_budget_exhausted: ["Investigation budget exhausted", "Presupuesto de investigación agotado"],
  source_identity_mismatch: ["Source revision mismatch", "La revisión del código no coincide"],
  unsupported_or_missing_exact_source_evidence: ["Unsupported or missing exact source evidence", "Evidencia exacta ausente o fuera del alcance"],
  source_parse_unavailable: ["Source parse unavailable", "Análisis sintáctico no disponible"],
  source_file_binding_mismatch: ["Source file binding mismatch", "La vinculación del archivo no coincide"],
  source_line_missing: ["Source line missing", "Falta la línea del código"],
  rule_semantics_require_specialist_review: ["Rule requires specialist analysis", "La regla requiere análisis especializado"],
  rule_source_line_mismatch: ["Rule and source line do not match", "La regla no coincide con la línea del código"],
  ambiguous_call_expression: ["Ambiguous call expression", "Expresión de llamada ambigua"],
  retained_observation_invalid: ["Retained observation invalid", "Observación conservada inválida"],
};

const sourceAvailabilityLabels: Record<string, [string, string]> = {
  "capture_deadline": ["Capture reached its deadline at this path", "La captura alcanzó su plazo en esta ruta"],
  "inventory_missing_or_unsupported": ["Path absent from supported regular-file inventory", "La ruta no figura en el inventario de archivos regulares compatibles"],
  "file_size_limit": ["Source exceeded the per-file capture limit", "El código superó el límite de captura por archivo"],
  "input_size_limit": ["Source exceeded the remaining aggregate input allowance", "El código superó el límite restante de entrada total"],
  "inventory_entry_invalid": ["Retained capture rejected an invalid inventory entry", "La captura rechazó una entrada de inventario inválida"],
  "blob_integrity_unavailable": ["Captured blob bytes did not pass identity validation", "Los bytes capturados no superaron la validación de identidad"],
  "observation_output_limit": ["Observation exceeded remaining retained output allowance", "La observación superó el límite restante de salida conservada"],
  "capture_operation_failed": ["Capture operation failed at this path; cause unspecified", "La operación de captura falló en esta ruta; causa sin especificar"],

  "source_not_retained": [
    "No observation retained for this candidate path; cause unknown",
    "No se conservó una observación para esta ruta; causa desconocida"
  ],
  "capture_observations_invalid": [
    "Retained observation collection is unavailable or malformed",
    "La colección de observaciones conservadas no está disponible o es inválida"
  ],
  "candidate_path_unusable": [
    "Candidate path cannot be safely matched",
    "La ruta del candidato no se puede vincular de forma segura"
  ],
  "observation_parse_unavailable": [
    "Retained observation reports parsing unavailable",
    "La observación conservada informa que el análisis sintáctico no está disponible"
  ],
  "observation_size_limit": [
    "Retained observation reports a source size limit",
    "La observación conservada informa un límite de tamaño del código"
  ],
  "observation_binding_invalid": [
    "Retained observation reports invalid source binding",
    "La observación conservada informa una vinculación del código inválida"
  ],
  "observation_scope_conflict": [
    "Retained observation binding conflicts with the expected source",
    "La vinculación de la observación conservada contradice el código esperado"
  ],
  "observation_status_unknown": [
    "Retained observation status is missing or unsupported",
    "El estado de la observación conservada falta o no es compatible"
  ],
  "not_recorded": [
    "Source availability detail was not retained",
    "No se conservó el detalle de disponibilidad del código"
  ]
};

const recommendations: Record<string, [string, string]> = {
  individual_material_review: ["Prioritize individual risk review", "Priorizar revisión individual del riesgo"],
  resolve_evidence_gaps: ["Resolve evidence gaps before disposition", "Resolver brechas de evidencia antes de decidir"],
  review_nonblocking_proposal: ["Review retained nonblocking proposal", "Revisar propuesta conservada de no bloqueo"],
};
const limitations: Record<string, [string, string]> = {
  run_scope_unverified: ["Exact run identity missing", "Falta la identidad de la ejecución exacta"],
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
  const investigation = value.source_investigation;
  const sourcePackets = new Map((investigation?.packets || []).map(p => [p.candidate_id, p]));
  const pages = Math.max(1, Math.ceil(value.queue.length / 25));
  const current = Math.min(page, pages - 1);
  return <section aria-label={es ? "Asistencia para revisión" : "Review assistance"}>
    <h3>{es ? "Cola priorizada de revisión asistida" : "Prioritized assisted-review queue"}</h3>
    <p>{investigation?.available ? (es ? "Investigación acotada del código conservada durante la evaluación; sin consultas a modelos. Cada disposición sigue siendo humana." : "Bounded source investigation retained during assessment; no model calls. Every disposition remains human.") : es ? "Análisis determinista conservado; no se realizó una nueva investigación del código ni se consultó un modelo. Los enlaces son ubicaciones, no prueba de inspección. Cada disposición sigue siendo humana." : "Retained deterministic analysis; no new source investigation or model call was performed. Links are locators, not proof of inspection. Every disposition remains human."}</p>
    <p>{value.pending_record_count} {es ? "registros pendientes. Los grupos comparten un perfil de revisión; no demuestran equivalencia ni permiten descartar candidatos." : "pending records. Groups share a review profile; they do not establish equivalence or permit candidate dismissal."}</p>
    {investigation?.available ? <p>{investigation.completed_count} / {investigation.candidate_count} {es ? "candidatos con análisis acotado de reglas; el resto requiere evidencia o análisis adicional. No demuestra seguridad ni explotabilidad." : "candidates with bounded rule analysis; the remainder need evidence or further analysis. This does not establish safety or exploitability."}</p> : null}
    {investigation?.available && investigation.source_availability_counts ? <div>
      <p>{es ? "Detalle de candidatos sin análisis sintáctico disponible; una observación ausente no demuestra un fallo del analizador ni una causa presupuestaria." : "Detail for candidates without available source parsing; an absent observation proves neither parser failure nor a budget cause."}</p>
      <ul aria-label={es ? "Disponibilidad del código" : "Source availability"}>
        {Object.entries(sourceAvailabilityLabels).map(([code, labels]) => {
          const count = investigation.source_availability_counts?.[code];
          return Number.isSafeInteger(count) && count! > 0 && count! <= (investigation.candidate_count ?? 0)
            ? <li key={code}>{labels[language]}: {count}</li> : null;
        })}
      </ul>
    </div> : null}
    <ol start={current * 25 + 1}>
      {value.queue.slice(current * 25, current * 25 + 25).map(packet => <li key={`${packet.record_index}:${packet.candidate_id}`}>
        <details data-review-assistance-candidate={packet.candidate_id}>
          <summary><code>{packet.candidate_id}</code> — {(Object.hasOwn(recommendations, packet.recommendation) ? recommendations[packet.recommendation] : recommendations.resolve_evidence_gaps)[language]}</summary>
          {packet.source_url && /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/blob\/[0-9a-f]{40}\//.test(packet.source_url) ? <p><a href={packet.source_url} target="_blank" rel="noopener noreferrer">{es ? "Abrir ubicación del código exacto" : "Open exact source location"}</a></p> : null}
          <ul>{packet.limitations.map(code => <li key={code}>{(Object.hasOwn(limitations, code) ? limitations[code] : ["Additional evidence review required", "Se requiere revisión adicional de evidencia"])[language]}</li>)}</ul>
          {sourcePackets.has(packet.candidate_id) ? (() => {
            const source = sourcePackets.get(packet.candidate_id)!;
            if (!source.completed) return <p>{(Object.hasOwn(investigationReasons, source.reason) ? investigationReasons[source.reason] : ["Investigation unresolved", "Investigación sin resolver"])[language]}. {source.reason === "source_parse_unavailable" ? (Object.hasOwn(sourceAvailabilityLabels, source.source_availability_detail || "") ? sourceAvailabilityLabels[source.source_availability_detail!] : sourceAvailabilityLabels.not_recorded)[language] + ". " : ""}{es ? "Solicitar evidencia antes de decidir." : "Request evidence before disposition."}</p>;
            const assertion = source.rule_id === "B101";
            const imported = source.rule_id === "B404" || source.rule_id === "B405";
            return <div data-source-investigation="true">
              <p>{es ? "Evidencia y razonamiento" : "Evidence and rationale"}: {assertion ? (es ? "Se observó una aserción en la línea exacta; Python optimizado puede eliminarla." : "An assertion was observed at the exact line; optimized Python can remove it.") : imported ? (es ? "Se observó una importación de una familia de API que requiere revisión contextual." : "An import from an API family requiring contextual review was observed.") : (es ? "Se examinó una llamada y la forma de sus argumentos; no se estableció su comportamiento en ejecución." : "A call and its argument shape were examined; runtime behavior was not established.")}</p>
              <p>{es ? "Contraevidencia: la presencia de esta estructura no demuestra una vulnerabilidad ni permite descartarla." : "Counterevidence: this structure alone neither establishes a vulnerability nor clears the candidate."}</p>
              <p>{es ? "Preguntas pendientes: ¿es alcanzable en producción?, ¿recibe datos no confiables?, ¿qué controles independientes existen?" : "Open questions: is it production-reachable, does it receive untrusted input, and what independent controls exist?"}</p>
              <p>{es ? "Recomendación: conservar para revisión contextual humana." : "Recommendation: retain for human contextual review."}</p>
              <p><code>{source.source_path || "—"}</code> · {es ? "Línea" : "Line"}: {source.line} · SHA-256: <code>{source.source_sha256 && /^[0-9a-f]{64}$/.test(source.source_sha256) ? source.source_sha256 : "—"}</code></p>
            </div>;
          })() : null}
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
