import type {Locale, Section} from "./assessmentTypes";

const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];

/** Read-only presentation of retained evidence. Never derives a score or a measurement. */
export default function UnscoredSectionEvidence({section, locale}: {section: Section; locale: Locale}) {
  if (!["architecture_debt", "velocity_complexity"].includes(String(section.id))) return null;
  const architecture = section.id === "architecture_debt";
  const es = locale === "es-MX";
  const evidence = strings(section.evidence);
  const limitations = [...strings(section.unavailable), ...strings(section.findings)];
  const provenance = object(section.score_input_provenance);
  const reasons: Record<string, [string, string]> = {
    measured_score_missing: ["No measured architecture score was retained.", "No se conservó una puntuación medida de arquitectura."],
    measured_score_invalid: ["The retained architecture score input is invalid.", "El dato conservado para la puntuación de arquitectura no es válido."],
    score_input_identity_unproven: ["The score input is not proven to belong to this assessment and source revision.", "No se ha comprobado que el dato de puntuación corresponda a esta evaluación y revisión del código."],
  };
  const reasonKey = String(provenance.reason || "");
  const reason = Object.hasOwn(reasons, reasonKey) ? reasons[reasonKey][es ? 1 : 0] : null;
  return <section data-section-evidence={section.id}>
    <h4>{es ? "Qué se evaluó y qué falta" : "What was assessed and what is missing"}</h4>
    <p>{architecture
      ? (es ? "Las observaciones de código y complejidad conservadas describen únicamente la población inspeccionada. No establecen por sí solas la calidad de la arquitectura ni una valoración completa de la deuda técnica."
        : "Retained source and complexity observations describe only the inspected population. They do not by themselves establish architecture quality or a complete technical-debt assessment.")
      : (es ? "La configuración de CI y la complejidad son indicadores de capacidad, no mediciones de velocidad de entrega. Medir la velocidad requiere un período definido, elementos de trabajo comparables y fechas verificables de inicio y entrega; los conteos de actividad no sustituyen esos datos."
        : "CI configuration and complexity are capacity indicators, not measured delivery velocity. Measuring velocity requires a defined period, comparable work items and verifiable start and delivery timestamps; activity counts do not replace those inputs.")}</p>
    {reason ? <p>{reason}</p> : null}
    <p>{es ? "La evidencia parcial sigue siendo parcial; un dato ausente no equivale a cero. Esta vista no cambia las puntuaciones, las exclusiones ni los requisitos de revisión humana."
      : "Partial evidence remains partial; a missing value is not zero. This view does not change scores, exclusions or human-review requirements."}</p>
    <b>{es ? "Evidencia conservada (texto original)" : "Retained evidence (original text)"}</b>
    {evidence.length ? <ul>{evidence.map((line, index) => <li key={index} data-no-localize="true">{line}</li>)}</ul>
      : <p>{es ? "No hay observaciones detalladas conservadas en esta sección. No se infieren mediciones." : "No detailed observations are retained in this section. No measurements are inferred."}</p>}
    {limitations.length ? <><b>{es ? "Limitaciones conservadas (texto original)" : "Retained limitations (original text)"}</b><ul>{limitations.map((line, index) => <li key={index} data-no-localize="true">{line}</li>)}</ul></> : null}
  </section>;
}
