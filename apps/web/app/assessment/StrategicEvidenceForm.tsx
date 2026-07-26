"use client";

import styles from "./strategicEvidence.module.css";
import type {Locale} from "./assessmentTypes";
import {
  STRATEGIC_EVIDENCE_DEFINITIONS,
  emptyStrategicEvidenceModule,
  moduleCompleteness,
  type StrategicHumanEvidenceInput,
} from "./strategicEvidence";

const TEXT = {
  en: {
    eyebrow: "OPTIONAL STRATEGIC EVIDENCE",
    title: "Add the human evidence code cannot provide",
    summary: "Use this intake for executed QA, platform observations, stakeholder context, incidents, objectives, constraints, compliance, staffing, and accepted risks. Missing modules remain Not assessed and are never inferred from repository code.",
    included: "Include this module",
    excluded: "Explicitly exclude from scope",
    exclusion: "Exclusion rationale",
    reviewer: "Evidence reviewer or supplier",
    observed: "Observed or approved at",
    source: "Source reference",
    onePerLine: "One structured item per line",
    notAssessed: "Not assessed",
    partial: "Partial — more evidence required",
    complete: "Complete intake — human review required",
    excludedStatus: "Excluded with rationale",
    field: (name: string) => name.replaceAll("_", " "),
  },
  "es-MX": {
    eyebrow: "EVIDENCIA ESTRATÉGICA OPCIONAL",
    title: "Agrega la evidencia humana que el código no puede proporcionar",
    summary: "Usa esta captura para QA ejecutado, observaciones de plataformas, contexto de interesados, incidentes, objetivos, restricciones, cumplimiento, personal y riesgos aceptados. Los módulos faltantes permanecen como No evaluados y nunca se infieren del repositorio.",
    included: "Incluir este módulo",
    excluded: "Excluir explícitamente del alcance",
    exclusion: "Justificación de exclusión",
    reviewer: "Revisor o proveedor de evidencia",
    observed: "Fecha de observación o aprobación",
    source: "Referencia de la fuente",
    onePerLine: "Un elemento estructurado por línea",
    notAssessed: "No evaluado",
    partial: "Parcial — se requiere más evidencia",
    complete: "Captura completa — requiere revisión humana",
    excludedStatus: "Excluido con justificación",
    field: (name: string) => name.replaceAll("_", " "),
  },
} satisfies Record<Locale, Record<string, unknown>>;

function statusLabel(status: ReturnType<typeof moduleCompleteness>, locale: Locale): string {
  const copy = TEXT[locale] as typeof TEXT.en;
  if (status === "complete") return copy.complete;
  if (status === "partial") return copy.partial;
  if (status === "excluded") return copy.excludedStatus;
  return copy.notAssessed;
}

export default function StrategicEvidenceForm({
  locale,
  value,
  onChange,
  disabled,
}: {
  locale: Locale;
  value: StrategicHumanEvidenceInput;
  onChange: (value: StrategicHumanEvidenceInput) => void;
  disabled?: boolean;
}) {
  const copy = TEXT[locale] as typeof TEXT.en;

  function setModule(moduleId: string, next: StrategicHumanEvidenceInput[string] | null): void {
    const updated = {...value};
    if (next) updated[moduleId] = next;
    else delete updated[moduleId];
    onChange(updated);
  }

  return <section className={styles.strategicEvidence} aria-labelledby="strategic-evidence-title">
    <div className={styles.strategicEvidenceHead}>
      <div>
        <p className="eyebrow">{copy.eyebrow}</p>
        <h3 id="strategic-evidence-title">{copy.title}</h3>
      </div>
      <span className="status gray">
        {Object.keys(value).length}/{STRATEGIC_EVIDENCE_DEFINITIONS.length}
      </span>
    </div>
    <p className="summary-box">{copy.summary}</p>

    <div className={styles.evidenceModuleGrid}>
      {STRATEGIC_EVIDENCE_DEFINITIONS.map((definition) => {
        const module = value[definition.moduleId];
        const status = moduleCompleteness(definition, module);
        return <details className={styles.evidenceModule} key={definition.moduleId}>
          <summary>
            <span>
              <b>{definition.label[locale]}</b>
              <small>{definition.description[locale]}</small>
            </span>
            <span className={`status ${status === "complete" ? "green" : status === "partial" ? "yellow" : "gray"}`}>
              {statusLabel(status, locale)}
            </span>
          </summary>
          <label className="check-row">
            <input
              type="checkbox"
              checked={Boolean(module)}
              disabled={disabled}
              onChange={(event) => setModule(
                definition.moduleId,
                event.target.checked ? emptyStrategicEvidenceModule() : null,
              )}
            />
            {copy.included}
          </label>
          {module ? <div className={styles.evidenceModuleBody}>
            <div className="form-grid">
              <label>{copy.reviewer}
                <input
                  value={module.reviewer}
                  disabled={disabled}
                  onChange={(event) => setModule(definition.moduleId, {...module, reviewer: event.target.value})}
                />
              </label>
              <label>{copy.observed}
                <input
                  type="datetime-local"
                  value={module.observed_at}
                  disabled={disabled}
                  onChange={(event) => setModule(definition.moduleId, {...module, observed_at: event.target.value})}
                />
              </label>
              <label>{copy.source}
                <input
                  value={module.source_reference}
                  disabled={disabled}
                  placeholder="evidence://..."
                  onChange={(event) => setModule(definition.moduleId, {...module, source_reference: event.target.value})}
                />
              </label>
            </div>
            {definition.requiredFields.map((field) => <label key={field} className={styles.evidenceTextareaLabel}>
              <span>{copy.field(field)}</span>
              <small>{copy.onePerLine}</small>
              <textarea
                rows={4}
                value={(module.evidence[field] || []).join("\n")}
                disabled={disabled || module.excluded}
                onChange={(event) => setModule(definition.moduleId, {
                  ...module,
                  evidence: {
                    ...module.evidence,
                    [field]: event.target.value.split(/\r?\n/),
                  },
                })}
              />
            </label>)}
            <label className="check-row">
              <input
                type="checkbox"
                checked={module.excluded}
                disabled={disabled}
                onChange={(event) => setModule(definition.moduleId, {...module, excluded: event.target.checked})}
              />
              {copy.excluded}
            </label>
            {module.excluded ? <label className={styles.evidenceTextareaLabel}>
              <span>{copy.exclusion}</span>
              <textarea
                rows={3}
                value={module.exclusion_rationale}
                disabled={disabled}
                onChange={(event) => setModule(definition.moduleId, {...module, exclusion_rationale: event.target.value})}
              />
            </label> : null}
          </div> : null}
        </details>;
      })}
    </div>
  </section>;
}
