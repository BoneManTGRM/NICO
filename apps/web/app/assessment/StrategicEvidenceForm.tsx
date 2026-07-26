"use client";

import styles from "./strategicEvidence.module.css";
import type {Locale} from "./assessmentTypes";
import {
  STRATEGIC_EVIDENCE_DEFINITIONS,
  emptyStrategicEvidenceModule,
  evidenceLines,
  moduleCompleteness,
  type StrategicHumanEvidenceInput,
} from "./strategicEvidence";

const TEXT = {
  en: {
    eyebrow: "OPTIONAL HUMAN EVIDENCE",
    title: "Add context the repository cannot provide",
    summary: "Include only the modules supported by observed, approved, or supplied evidence. Anything omitted remains Not assessed.",
    open: "Add strategic evidence",
    added: "modules added",
    ready: "ready for review",
    add: "Add evidence",
    remove: "Remove module",
    excluded: "Exclude from scope",
    exclusion: "Exclusion rationale",
    reviewer: "Reviewer or evidence supplier",
    observed: "Observed or approved at",
    source: "Source reference",
    metadata: "Evidence source",
    onePerLine: "One item per line",
    notAssessed: "Not assessed",
    partial: "Needs evidence",
    complete: "Ready for review",
    excludedStatus: "Excluded",
    field: (name: string) => name.replaceAll("_", " "),
  },
  "es-MX": {
    eyebrow: "EVIDENCIA HUMANA OPCIONAL",
    title: "Agrega el contexto que el repositorio no puede proporcionar",
    summary: "Incluye únicamente módulos respaldados por evidencia observada, aprobada o proporcionada. Lo omitido permanece como No evaluado.",
    open: "Agregar evidencia estratégica",
    added: "módulos agregados",
    ready: "listos para revisión",
    add: "Agregar evidencia",
    remove: "Eliminar módulo",
    excluded: "Excluir del alcance",
    exclusion: "Justificación de exclusión",
    reviewer: "Revisor o proveedor de evidencia",
    observed: "Fecha de observación o aprobación",
    source: "Referencia de la fuente",
    metadata: "Fuente de evidencia",
    onePerLine: "Un elemento por línea",
    notAssessed: "No evaluado",
    partial: "Falta evidencia",
    complete: "Listo para revisión",
    excludedStatus: "Excluido",
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

function statusTone(status: ReturnType<typeof moduleCompleteness>): string {
  if (status === "complete") return styles.statusComplete;
  if (status === "partial") return styles.statusPartial;
  if (status === "excluded") return styles.statusExcluded;
  return styles.statusEmpty;
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
  const addedCount = Object.keys(value).length;
  const readyCount = STRATEGIC_EVIDENCE_DEFINITIONS.filter((definition) => {
    const status = moduleCompleteness(definition, value[definition.moduleId]);
    return status === "complete" || status === "excluded";
  }).length;

  function setModule(
    moduleId: string,
    next: StrategicHumanEvidenceInput[string] | null,
  ): void {
    const updated = {...value};
    if (next) updated[moduleId] = next;
    else delete updated[moduleId];
    onChange(updated);
  }

  return <details className={styles.strategicEvidence}>
    <summary className={styles.intakeSummary}>
      <span className={styles.intakeIdentity}>
        <span className="eyebrow">{copy.eyebrow}</span>
        <strong>{copy.open}</strong>
        <small>{copy.summary}</small>
      </span>
      <span className={styles.intakeProgress} aria-label={`${addedCount} ${copy.added}; ${readyCount} ${copy.ready}`}>
        <b>{addedCount}/{STRATEGIC_EVIDENCE_DEFINITIONS.length}</b>
        <small>{readyCount} {copy.ready}</small>
      </span>
    </summary>

    <div className={styles.intakeBody}>
      <div className={styles.intakeHeading}>
        <h3>{copy.title}</h3>
        <p>{copy.summary}</p>
      </div>

      <div className={styles.evidenceModuleGrid}>
        {STRATEGIC_EVIDENCE_DEFINITIONS.map((definition) => {
          const module = value[definition.moduleId];
          const status = moduleCompleteness(definition, module);
          return <details className={styles.evidenceModule} key={definition.moduleId}>
            <summary>
              <span className={styles.moduleIdentity}>
                <b>{definition.label[locale]}</b>
                <small>{definition.description[locale]}</small>
              </span>
              <span className={`${styles.moduleStatus} ${statusTone(status)}`}>{statusLabel(status, locale)}</span>
            </summary>

            <div className={styles.evidenceModuleBody}>
              {!module ? <div className={styles.moduleEmptyState}>
                <p>{definition.description[locale]}</p>
                <button
                  type="button"
                  className={styles.addButton}
                  disabled={disabled}
                  onClick={() => setModule(definition.moduleId, emptyStrategicEvidenceModule())}
                >
                  {copy.add}
                </button>
              </div> : <>
                <fieldset className={styles.metadataGroup} disabled={disabled}>
                  <legend>{copy.metadata}</legend>
                  <div className={styles.metadataGrid}>
                    <label>{copy.reviewer}
                      <input
                        value={module.reviewer}
                        onChange={(event) => setModule(
                          definition.moduleId,
                          {...module, reviewer: event.target.value},
                        )}
                      />
                    </label>
                    <label>{copy.observed}
                      <input
                        type="datetime-local"
                        value={module.observed_at}
                        onChange={(event) => setModule(
                          definition.moduleId,
                          {...module, observed_at: event.target.value},
                        )}
                      />
                    </label>
                    <label className={styles.sourceField}>{copy.source}
                      <input
                        value={module.source_reference}
                        placeholder="evidence://..."
                        onChange={(event) => setModule(
                          definition.moduleId,
                          {...module, source_reference: event.target.value},
                        )}
                      />
                    </label>
                  </div>
                </fieldset>

                {!module.excluded ? <div className={styles.evidenceFields}>
                  {definition.requiredFields.map((field) => <label key={field} className={styles.evidenceTextareaLabel}>
                    <span>{copy.field(field)}</span>
                    <small>{copy.onePerLine}</small>
                    <textarea
                      rows={3}
                      value={(module.evidence[field] || []).join("\n")}
                      disabled={disabled}
                      onChange={(event) => setModule(definition.moduleId, {
                        ...module,
                        evidence: {
                          ...module.evidence,
                          [field]: evidenceLines(event.target.value),
                        },
                      })}
                    />
                  </label>)}
                </div> : null}

                <div className={styles.moduleActions}>
                  <label className={styles.excludeControl}>
                    <input
                      type="checkbox"
                      checked={module.excluded}
                      disabled={disabled}
                      onChange={(event) => setModule(
                        definition.moduleId,
                        {...module, excluded: event.target.checked},
                      )}
                    />
                    <span>{copy.excluded}</span>
                  </label>
                  <button
                    type="button"
                    className={styles.removeButton}
                    disabled={disabled}
                    onClick={() => setModule(definition.moduleId, null)}
                  >
                    {copy.remove}
                  </button>
                </div>

                {module.excluded ? <label className={styles.evidenceTextareaLabel}>
                  <span>{copy.exclusion}</span>
                  <textarea
                    rows={3}
                    value={module.exclusion_rationale}
                    disabled={disabled}
                    onChange={(event) => setModule(
                      definition.moduleId,
                      {...module, exclusion_rationale: event.target.value},
                    )}
                  />
                </label> : null}
              </>}
            </div>
          </details>;
        })}
      </div>
    </div>
  </details>;
}
