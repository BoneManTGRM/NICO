"use client";

import {useEffect, useState, type Dispatch, type SetStateAction} from "react";
import styles from "./strategicEvidence.module.css";
import type {Locale} from "./assessmentTypes";
import {
  type EngagementFieldKey,
  type EngagementFieldState,
  type EngagementFieldStates,
} from "./engagementFieldState";
import {
  STRATEGIC_EVIDENCE_DEFINITIONS,
  CLIENT_ENGAGEMENT_FIELDS,
  emptyStrategicEvidenceModule,
  evidenceFields,
  evidenceLines,
  moduleCompleteness,
  type StrategicHumanEvidenceInput,
} from "./strategicEvidence";

const MOBILE_CLIENT_ENGAGEMENT_FIELDS = ["access_method", "primary_technical_contact", "authorized_scope"] as const;

const EVIDENCE_FIELD_LABELS = {
  en: {
    test_cases: "Test cases",
    observed_results: "Observed results",
    matrix: "Coverage matrix",
    observations: "Observations",
    objectives: "Objectives",
    constraints: "Constraints",
    access_method: "Access Method",
    primary_technical_contact: "Primary Technical Contact",
    authorized_scope: "Authorized Scope",
    incidents: "Incidents",
    success_measures: "Success measures",
    requirements: "Requirements",
    authority_status: "Source authority status",
    decisions: "Decisions",
  },
  "es-MX": {
    test_cases: "Casos de prueba",
    observed_results: "Resultados observados",
    matrix: "Matriz de cobertura",
    observations: "Observaciones",
    objectives: "Objetivos",
    constraints: "Restricciones",
    access_method: "Método de acceso",
    primary_technical_contact: "Contacto técnico principal",
    authorized_scope: "Alcance autorizado",
    incidents: "Incidentes",
    success_measures: "Medidas de éxito",
    requirements: "Requisitos",
    authority_status: "Estado de autoridad de la fuente",
    decisions: "Decisiones",
  },
} satisfies Record<Locale, Record<string, string>>;

const UNKNOWN_EVIDENCE_FIELD_LABEL = {
  en: "Additional evidence",
  "es-MX": "Evidencia adicional",
} satisfies Record<Locale, string>;

function evidenceFieldLabel(name: string, locale: Locale): string {
  return EVIDENCE_FIELD_LABELS[locale][name] || UNKNOWN_EVIDENCE_FIELD_LABEL[locale];
}

const TEXT = {
  en: {
    eyebrow: "OPTIONAL HUMAN EVIDENCE",
    title: "Add context the repository cannot provide",
    summary: "Add only the evidence available for this engagement. Missing modules remain Not assessed and are never inferred from repository code.",
    modules: "Evidence modules",
    mobileOptional: "Optional",
    mobileContextLabel: "Optional client context",
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
    mobileStable: "The full optional evidence editor is not loaded on phones or touch-first devices. Client and project names above are optional display metadata and do not make the fields below required. Add only the client context available for this assessment.",
    mobileClientTitle: "Optional client context",
    mobileClientBody: "For the standard public assessment, Access Method, Primary Technical Contact, and Authorized Scope are optional context. Missing values remain unassessed and are never inferred or fabricated.",
    field: (name: string) => evidenceFieldLabel(name, "en"),
  },
  "es-MX": {
    eyebrow: "EVIDENCIA HUMANA OPCIONAL",
    title: "Agrega el contexto que el repositorio no puede proporcionar",
    summary: "Agrega únicamente la evidencia disponible para este encargo. Los módulos faltantes permanecen como No evaluados y nunca se infieren del repositorio.",
    modules: "Módulos de evidencia",
    mobileOptional: "Opcional",
    mobileContextLabel: "Contexto opcional del cliente",
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
    mobileStable: "El editor completo de evidencia opcional no se carga en teléfonos ni dispositivos principalmente táctiles. Los nombres de cliente y proyecto de arriba son metadatos de presentación opcionales y no hacen obligatorios los campos de abajo. Agrega únicamente el contexto del cliente disponible para esta evaluación.",
    mobileClientTitle: "Contexto opcional del cliente",
    mobileClientBody: "En la evaluación pública estándar, Método de acceso, Contacto técnico principal y Alcance autorizado son contexto opcional. Los valores faltantes permanecen sin evaluar y nunca se infieren ni se inventan.",
    field: (name: string) => evidenceFieldLabel(name, "es-MX"),
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

function useRichEvidenceEditor(): boolean {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1025px) and (pointer: fine)");
    const synchronize = () => setEnabled(query.matches);
    synchronize();
    query.addEventListener?.("change", synchronize);
    return () => query.removeEventListener?.("change", synchronize);
  }, []);

  return enabled;
}

export default function StrategicEvidenceForm({
  locale,
  value,
  onChange,
  engagementFieldStates,
  onEngagementFieldValueChange,
  onEngagementFieldStateChange,
  disabled,
}: {
  locale: Locale;
  value: StrategicHumanEvidenceInput;
  onChange: Dispatch<SetStateAction<StrategicHumanEvidenceInput>>;
  engagementFieldStates: EngagementFieldStates;
  onEngagementFieldValueChange: (
    field: EngagementFieldKey,
    value: string,
  ) => void;
  onEngagementFieldStateChange: (
    field: EngagementFieldKey,
    state: EngagementFieldState,
  ) => void;
  disabled?: boolean;
}) {
  const copy = TEXT[locale] as typeof TEXT.en;
  const richEditorEnabled = useRichEvidenceEditor();
  const [activeModuleId, setActiveModuleId] = useState(
    STRATEGIC_EVIDENCE_DEFINITIONS[0]?.moduleId || "",
  );
  const addedCount = Object.keys(value).length;

  function setModule(
    moduleId: string,
    next: StrategicHumanEvidenceInput[string] | null | (
      (current: StrategicHumanEvidenceInput[string]) =>
        StrategicHumanEvidenceInput[string] | null
    ),
  ): void {
    onChange((currentValue) => {
      const currentModule = currentValue[moduleId] || emptyStrategicEvidenceModule();
      const resolved = typeof next === "function" ? next(currentModule) : next;
      const updated = {...currentValue};
      if (resolved) updated[moduleId] = resolved;
      else delete updated[moduleId];
      return updated;
    });
  }

  function setEvidenceField(moduleId: string, field: string, items: string[]): void {
    setModule(moduleId, (current) => ({
      ...current,
      evidence: {
        ...current.evidence,
        [field]: items,
      },
    }));
  }

  // The intake editor is never needed while an exact run is active. Removing it from
  // the DOM prevents Safari from repainting disabled evidence controls on every poll.
  if (disabled) return null;

  if (!richEditorEnabled) {
    const engagement = value.stakeholder_context || emptyStrategicEvidenceModule();
    return <section
      className={styles.strategicEvidence}
      aria-labelledby="strategic-evidence-title"
      data-mobile-evidence-boundary="true"
      data-evidence-editor-mounted="false"
      data-mobile-client-engagement-context="true"
    >
      <div className={styles.strategicEvidenceHead}>
        <div className={styles.headingCopy}>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h3 id="strategic-evidence-title">{copy.title}</h3>
          <p>{copy.summary}</p>
        </div>
        <div className={styles.progressSummary} aria-label={`${copy.mobileOptional}: ${copy.mobileContextLabel}`}>
          <strong>{copy.mobileOptional}</strong>
          <span>{copy.mobileContextLabel}</span>
        </div>
      </div>
      <p className="muted" data-mobile-evidence-note="true">{copy.mobileStable}</p>
      <div className={styles.moduleEditor}>
        <header className={styles.moduleEditorHead}>
          <div>
            <span className={styles.selectedLabel}>{copy.mobileClientTitle}</span>
            <p>{copy.mobileClientBody}</p>
          </div>
        </header>
        <div className={styles.requiredEvidence}>
          {MOBILE_CLIENT_ENGAGEMENT_FIELDS.map((field) => <label
            key={field}
            className={styles.evidenceTextareaLabel}
            data-engagement-field={field}
            data-engagement-state={engagementFieldStates[field].state}
          >
            <span>{copy.field(field)}</span>
            <input
              type="text"
              value={(engagement.evidence[field] || [])[0] || ""}
              disabled={disabled}
              autoComplete="off"
              style={{
                width: "100%",
                minHeight: 43,
                padding: "9px 11px",
                border: "1px solid rgba(71, 85, 105, 0.86)",
                borderRadius: 10,
                background: "rgba(2, 6, 23, 0.76)",
                color: "#f8fafc",
                font: "inherit",
              }}
              onChange={(event) => onEngagementFieldValueChange(
                field,
                event.target.value,
              )}
            />
          </label>)}
        </div>
      </div>
    </section>;
  }

  const activeDefinition = STRATEGIC_EVIDENCE_DEFINITIONS.find(
    (definition) => definition.moduleId === activeModuleId,
  ) || STRATEGIC_EVIDENCE_DEFINITIONS[0];
  const activeModule = activeDefinition ? value[activeDefinition.moduleId] : undefined;
  const activeStatus = activeDefinition
    ? moduleCompleteness(activeDefinition, activeModule)
    : "not_assessed";

  function addModule(excluded = false): void {
    if (!activeDefinition) return;
    setModule(activeDefinition.moduleId, {
      ...emptyStrategicEvidenceModule(),
      excluded,
    });
    if (activeDefinition.moduleId === "stakeholder_context" && excluded) {
      for (const field of MOBILE_CLIENT_ENGAGEMENT_FIELDS) {
        onEngagementFieldStateChange(field, "excluded_from_scope");
      }
    }
  }

  if (!activeDefinition) return null;

  return <section
    className={styles.strategicEvidence}
    aria-labelledby="strategic-evidence-title"
    data-evidence-editor-mounted="true"
  >
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
                onChange={(event) => {
                  const reviewer = event.target.value;
                  setModule(activeDefinition.moduleId, (current) => ({...current, reviewer}));
                }}
              />
            </label>
            <label>{copy.observed}
              <input
                type="datetime-local"
                value={activeModule.observed_at}
                disabled={disabled}
                onChange={(event) => {
                  const observed_at = event.target.value;
                  setModule(activeDefinition.moduleId, (current) => ({...current, observed_at}));
                }}
              />
            </label>
            <label>{copy.source}
              <input
                value={activeModule.source_reference}
                disabled={disabled}
                placeholder="evidence://..."
                onChange={(event) => {
                  const source_reference = event.target.value;
                  setModule(activeDefinition.moduleId, (current) => ({...current, source_reference}));
                }}
              />
            </label>
          </div>

          {activeModule.excluded ? <label className={styles.evidenceTextareaLabel}>
            <span>{copy.exclusion}</span>
            <textarea
              rows={4}
              value={activeModule.exclusion_rationale}
              disabled={disabled}
              onChange={(event) => {
                const exclusion_rationale = event.target.value;
                setModule(activeDefinition.moduleId, (current) => ({...current, exclusion_rationale}));
              }}
            />
          </label> : <div className={styles.requiredEvidence}>
            {evidenceFields(activeDefinition).map((field) => {
              const isEngagementField = CLIENT_ENGAGEMENT_FIELDS.has(field);
              return <label
                key={field}
                className={styles.evidenceTextareaLabel}
                {...(isEngagementField
                  ? {
                      "data-engagement-field": field,
                      "data-engagement-state": engagementFieldStates[
                        field as EngagementFieldKey
                      ].state,
                    }
                  : {})}
              >
                <span>{copy.field(field)}</span>
                <small>{copy.onePerLine}</small>
                <textarea
                  rows={4}
                  value={(activeModule.evidence[field] || []).join("\n")}
                  disabled={disabled}
                  onChange={(event) => {
                    if (isEngagementField) {
                      onEngagementFieldValueChange(
                        field as EngagementFieldKey,
                        event.target.value,
                      );
                    } else {
                      setEvidenceField(
                        activeDefinition.moduleId,
                        field,
                        evidenceLines(event.target.value),
                      );
                    }
                  }}
                />
              </label>;
            })}
          </div>}

          <footer className={styles.moduleActions}>
            <button
              type="button"
              className={styles.secondaryAction}
              disabled={disabled}
              onClick={() => {
                const excluded = !activeModule.excluded;
                setModule(activeDefinition.moduleId, (current) => ({...current, excluded}));
                if (activeDefinition.moduleId === "stakeholder_context") {
                  for (const field of MOBILE_CLIENT_ENGAGEMENT_FIELDS) {
                    onEngagementFieldStateChange(
                      field,
                      excluded ? "excluded_from_scope" : "not_supplied",
                    );
                  }
                }
              }}
            >
              {activeModule.excluded ? copy.includeInstead : copy.excludeModule}
            </button>
            <button
              type="button"
              className={styles.ghostAction}
              disabled={disabled}
              onClick={() => {
                setModule(activeDefinition.moduleId, null);
                if (activeDefinition.moduleId === "stakeholder_context") {
                  for (const field of MOBILE_CLIENT_ENGAGEMENT_FIELDS) {
                    onEngagementFieldStateChange(field, "not_supplied");
                  }
                }
              }}
            >
              {copy.removeModule}
            </button>
          </footer>
        </div>}
      </article>
    </div>
  </section>;
}
