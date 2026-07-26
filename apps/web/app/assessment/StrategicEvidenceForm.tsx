"use client";

import {useState} from "react";
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
    summary: "Add only the evidence available for this engagement. Missing modules remain Not assessed and are never inferred from repository code.",
    modules: "Evidence modules",
    chooseModule: "Choose an evidence module",
    added: (count: number, total: number) => `${count} of ${total} modules added`,
    selected: "Selected module",
    exclusion: "Exclusion rationale",
    reviewer: "Reviewer or evidence supplier",
    observed: "Observed or approved at",
    source: "Source reference",
    onePerLine: "One structured item per line",
    notAssessed: "Not assessed",
    partial: "More evidence required",
    complete: "Ready for review",
    excludedStatus: "Excluded with rationale",
    addEvidence: "Add evidence",
    excludeModule: "Exclude from scope",
    includeInstead: "Include evidence instead",
    removeModule: "Remove from intake",
    emptyTitle: "No evidence added for this module",
    emptyBody: "Add human-observed information when it is available, or exclude the module only when an explicit rationale exists.",
    field: (name: string) => name.replaceAll("_", " "),
  },
  "es-MX": {
    eyebrow: "EVIDENCIA HUMANA OPCIONAL",
    title: "Agrega el contexto que el repositorio no puede proporcionar",
    summary: "Agrega únicamente la evidencia disponible para este encargo. Los módulos faltantes permanecen como No evaluados y nunca se infieren del repositorio.",
    modules: "Módulos de evidencia",
    chooseModule: "Elige un módulo de evidencia",
    added: (count: number, total: number) => `${count} de ${total} módulos agregados`,
    selected: "Módulo seleccionado",
    exclusion: "Justificación de exclusión",
    reviewer: "Revisor o proveedor de evidencia",
    observed: "Fecha de observación o aprobación",
    source: "Referencia de la fuente",
    onePerLine: "Un elemento estructurado por línea",
    notAssessed: "No evaluado",
    partial: "Se requiere más evidencia",
    complete: "Listo para revisión",
    excludedStatus: "Excluido con justificación",
    addEvidence: "Agregar evidencia",
    excludeModule: "Excluir del alcance",
    includeInstead: "Incluir evidencia en su lugar",
    removeModule: "Quitar de la captura",
    emptyTitle: "No se agregó evidencia para este módulo",
    emptyBody: "Agrega información observada por una persona cuando esté disponible, o excluye el módulo únicamente con una justificación explícita.",
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

function statusClass(status: ReturnType<typeof moduleCompleteness>): string {
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
  const [activeModuleId, setActiveModuleId] = useState(
    STRATEGIC_EVIDENCE_DEFINITIONS[0]?.moduleId || "",
  );
  const activeDefinition = STRATEGIC_EVIDENCE_DEFINITIONS.find(
    (definition) => definition.moduleId === activeModuleId,
  ) || STRATEGIC_EVIDENCE_DEFINITIONS[0];
  const activeModule = activeDefinition ? value[activeDefinition.moduleId] : undefined;
  const activeStatus = activeDefinition
    ? moduleCompleteness(activeDefinition, activeModule)
    : "not_assessed";
  const addedCount = Object.keys(value).length;

  function setModule(
    moduleId: string,
    next: StrategicHumanEvidenceInput[string] | null,
  ): void {
    const updated = {...value};
    if (next) updated[moduleId] = next;
    else delete updated[moduleId];
    onChange(updated);
  }

  function addModule(excluded = false): void {
    if (!activeDefinition) return;
    setModule(activeDefinition.moduleId, {
      ...emptyStrategicEvidenceModule(),
      excluded,
    });
  }

  if (!activeDefinition) return null;

  return <section className={styles.strategicEvidence} aria-labelledby="strategic-evidence-title">
    <div className={styles.strategicEvidenceHead}>
      <div className={styles.headingCopy}>
        <p className="eyebrow">{copy.eyebrow}</p>
        <h3 id="strategic-evidence-title">{copy.title}</h3>
        <p>{copy.summary}</p>
      </div>
      <div className={styles.progressSummary} aria-label={copy.added(addedCount, STRATEGIC_EVIDENCE_DEFINITIONS.length)}>
        <strong>{addedCount}/{STRATEGIC_EVIDENCE_DEFINITIONS.length}</strong>
        <span>{copy.modules}</span>
      </div>
    </div>

    <label className={styles.mobileChooser}>
      <span>{copy.chooseModule}</span>
      <select
        value={activeDefinition.moduleId}
        disabled={disabled}
        onChange={(event) => setActiveModuleId(event.target.value)}
      >
        {STRATEGIC_EVIDENCE_DEFINITIONS.map((definition) => (
          <option value={definition.moduleId} key={definition.moduleId}>
            {definition.label[locale]} — {statusLabel(moduleCompleteness(definition, value[definition.moduleId]), locale)}
          </option>
        ))}
      </select>
    </label>

    <div className={styles.evidenceWorkspace}>
      <nav className={styles.moduleList} aria-label={copy.modules}>
        {STRATEGIC_EVIDENCE_DEFINITIONS.map((definition) => {
          const status = moduleCompleteness(definition, value[definition.moduleId]);
          const active = definition.moduleId === activeDefinition.moduleId;
          return <button
            type="button"
            className={`${styles.moduleButton} ${active ? styles.moduleButtonActive : ""}`}
            aria-pressed={active}
            disabled={disabled}
            onClick={() => setActiveModuleId(definition.moduleId)}
            key={definition.moduleId}
          >
            <span className={`${styles.statusDot} ${statusClass(status)}`} aria-hidden="true" />
            <span className={styles.moduleButtonCopy}>
              <strong>{definition.label[locale]}</strong>
              <small>{statusLabel(status, locale)}</small>
            </span>
          </button>;
        })}
      </nav>

      <article className={styles.moduleEditor} aria-labelledby={`strategic-evidence-${activeDefinition.moduleId}`}>
        <header className={styles.moduleEditorHead}>
          <div>
            <span className={styles.selectedLabel}>{copy.selected}</span>
            <h4 id={`strategic-evidence-${activeDefinition.moduleId}`}>{activeDefinition.label[locale]}</h4>
            <p>{activeDefinition.description[locale]}</p>
          </div>
          <span className={`${styles.statusBadge} ${statusClass(activeStatus)}`}>{statusLabel(activeStatus, locale)}</span>
        </header>

        {!activeModule ? <div className={styles.emptyModule}>
          <div>
            <strong>{copy.emptyTitle}</strong>
            <p>{copy.emptyBody}</p>
          </div>
          <div className={styles.emptyActions}>
            <button type="button" className={styles.primaryAction} disabled={disabled} onClick={() => addModule(false)}>
              {copy.addEvidence}
            </button>
            <button type="button" className={styles.secondaryAction} disabled={disabled} onClick={() => addModule(true)}>
              {copy.excludeModule}
            </button>
          </div>
        </div> : <div className={styles.evidenceModuleBody}>
          <div className={styles.metadataGrid}>
            <label>{copy.reviewer}
              <input
                value={activeModule.reviewer}
                disabled={disabled}
                onChange={(event) => setModule(
                  activeDefinition.moduleId,
                  {...activeModule, reviewer: event.target.value},
                )}
              />
            </label>
            <label>{copy.observed}
              <input
                type="datetime-local"
                value={activeModule.observed_at}
                disabled={disabled}
                onChange={(event) => setModule(
                  activeDefinition.moduleId,
                  {...activeModule, observed_at: event.target.value},
                )}
              />
            </label>
            <label>{copy.source}
              <input
                value={activeModule.source_reference}
                disabled={disabled}
                placeholder="evidence://..."
                onChange={(event) => setModule(
                  activeDefinition.moduleId,
                  {...activeModule, source_reference: event.target.value},
                )}
              />
            </label>
          </div>

          {activeModule.excluded ? <label className={styles.evidenceTextareaLabel}>
            <span>{copy.exclusion}</span>
            <textarea
              rows={4}
              value={activeModule.exclusion_rationale}
              disabled={disabled}
              onChange={(event) => setModule(
                activeDefinition.moduleId,
                {...activeModule, exclusion_rationale: event.target.value},
              )}
            />
          </label> : <div className={styles.requiredEvidence}>
            {activeDefinition.requiredFields.map((field) => <label key={field} className={styles.evidenceTextareaLabel}>
              <span>{copy.field(field)}</span>
              <small>{copy.onePerLine}</small>
              <textarea
                rows={4}
                value={(activeModule.evidence[field] || []).join("\n")}
                disabled={disabled}
                onChange={(event) => setModule(activeDefinition.moduleId, {
                  ...activeModule,
                  evidence: {
                    ...activeModule.evidence,
                    [field]: evidenceLines(event.target.value),
                  },
                })}
              />
            </label>)}
          </div>}

          <footer className={styles.moduleActions}>
            <button
              type="button"
              className={styles.secondaryAction}
              disabled={disabled}
              onClick={() => setModule(activeDefinition.moduleId, {
                ...activeModule,
                excluded: !activeModule.excluded,
              })}
            >
              {activeModule.excluded ? copy.includeInstead : copy.excludeModule}
            </button>
            <button
              type="button"
              className={styles.removeAction}
              disabled={disabled}
              onClick={() => setModule(activeDefinition.moduleId, null)}
            >
              {copy.removeModule}
            </button>
          </footer>
        </div>}
      </article>
    </div>
  </section>;
}
