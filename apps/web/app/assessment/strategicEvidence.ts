import type {Locale} from "./assessmentTypes";

export type StrategicEvidenceModuleInput = {
  evidence: Record<string, string[]>;
  reviewer: string;
  observed_at: string;
  source_reference: string;
  excluded: boolean;
  exclusion_rationale: string;
};

export type StrategicHumanEvidenceInput = Record<string, StrategicEvidenceModuleInput>;

export type StrategicEvidenceDefinition = {
  moduleId: string;
  label: Record<Locale, string>;
  description: Record<Locale, string>;
  requiredFields: string[];
};

// This list mirrors nico.decision_grade_human_evidence_v1.MODULE_DEFINITIONS.
// Keep the exact module IDs and required fields synchronized with the backend contract.
export const STRATEGIC_EVIDENCE_DEFINITIONS: StrategicEvidenceDefinition[] = [
  {
    moduleId: "functional_qa",
    label: {en: "Functional QA", "es-MX": "QA funcional"},
    description: {
      en: "Human-observed test cases and actual results for important user journeys.",
      "es-MX": "Casos de prueba observados por personas y resultados reales de recorridos importantes.",
    },
    requiredFields: ["test_cases", "observed_results"],
  },
  {
    moduleId: "platform_parity",
    label: {en: "Browser, device, and platform parity", "es-MX": "Paridad de navegador, dispositivo y plataforma"},
    description: {
      en: "Observed behavior across supported browsers, devices, operating systems, and application surfaces.",
      "es-MX": "Comportamiento observado en navegadores, dispositivos, sistemas operativos y superficies compatibles.",
    },
    requiredFields: ["matrix"],
  },
  {
    moduleId: "accessibility_ux",
    label: {en: "Accessibility and UX review", "es-MX": "Revisión de accesibilidad y experiencia de usuario"},
    description: {
      en: "Accessibility, task-completion, workflow-friction, and recovery observations.",
      "es-MX": "Observaciones de accesibilidad, finalización de tareas, fricción del flujo y recuperación.",
    },
    requiredFields: ["observations"],
  },
  {
    moduleId: "stakeholder_context",
    label: {en: "Stakeholder objectives and constraints", "es-MX": "Objetivos y restricciones de las partes interesadas"},
    description: {
      en: "Named objectives, pain points, operating constraints, desired state, and decision priorities.",
      "es-MX": "Objetivos, problemas, restricciones operativas, estado deseado y prioridades de decisión.",
    },
    requiredFields: ["objectives", "constraints"],
  },
  {
    moduleId: "incident_history",
    label: {en: "Incident and support history", "es-MX": "Historial de incidentes y soporte"},
    description: {
      en: "Human-confirmed incidents, customer-impacting defects, support themes, and operational consequences.",
      "es-MX": "Incidentes confirmados, defectos con impacto al cliente, temas de soporte y consecuencias operativas.",
    },
    requiredFields: ["incidents"],
  },
  {
    moduleId: "product_objectives",
    label: {en: "Product objectives and release outcomes", "es-MX": "Objetivos del producto y resultados del lanzamiento"},
    description: {
      en: "Target outcomes and success measures used to connect technical findings to product decisions.",
      "es-MX": "Resultados objetivo y medidas de éxito para conectar hallazgos técnicos con decisiones del producto.",
    },
    requiredFields: ["objectives", "success_measures"],
  },
  {
    moduleId: "release_constraints",
    label: {en: "Release deadlines and delivery constraints", "es-MX": "Fechas y restricciones de entrega"},
    description: {
      en: "Deadlines, contractual commitments, rollout constraints, rollback limits, and dependency dates.",
      "es-MX": "Fechas límite, compromisos contractuales, restricciones de despliegue, límites de reversión y dependencias.",
    },
    requiredFields: ["constraints"],
  },
  {
    moduleId: "compliance_requirements",
    label: {en: "Regulatory and contractual requirements", "es-MX": "Requisitos normativos y contractuales"},
    description: {
      en: "Explicit obligations supplied by authorized stakeholders; this is readiness evidence, not certification.",
      "es-MX": "Obligaciones explícitas proporcionadas por partes autorizadas; es evidencia de preparación, no certificación.",
    },
    requiredFields: ["requirements"],
  },
  {
    moduleId: "budget_staffing",
    label: {en: "Budget, staffing, and capacity constraints", "es-MX": "Restricciones de presupuesto, personal y capacidad"},
    description: {
      en: "Available roles, capacity, budget ranges, hiring constraints, and delivery ownership assumptions.",
      "es-MX": "Roles disponibles, capacidad, rangos presupuestarios, contratación y supuestos de responsabilidad.",
    },
    requiredFields: ["constraints"],
  },
  {
    moduleId: "accepted_risks",
    label: {en: "Known decisions and accepted risks", "es-MX": "Decisiones conocidas y riesgos aceptados"},
    description: {
      en: "Named, time-bounded risk acceptances and architecture decisions with owner and rationale.",
      "es-MX": "Aceptaciones de riesgo y decisiones de arquitectura con responsable, plazo y justificación.",
    },
    requiredFields: ["decisions"],
  },
];

export function emptyStrategicEvidenceModule(): StrategicEvidenceModuleInput {
  return {
    evidence: {},
    reviewer: "",
    observed_at: "",
    source_reference: "",
    excluded: false,
    exclusion_rationale: "",
  };
}

export function evidenceLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 100);
}

export function moduleCompleteness(
  definition: StrategicEvidenceDefinition,
  value: StrategicEvidenceModuleInput | undefined,
): "not_assessed" | "partial" | "complete" | "excluded" {
  if (!value) return "not_assessed";
  if (value.excluded && value.exclusion_rationale.trim()) return "excluded";
  const fieldsComplete = definition.requiredFields.every(
    (field) => (value.evidence[field] || []).some((item) => item.trim()),
  );
  const metadataComplete = Boolean(
    value.reviewer.trim() && value.observed_at.trim() && value.source_reference.trim(),
  );
  return fieldsComplete && metadataComplete && !value.excluded ? "complete" : "partial";
}

export function compactStrategicHumanEvidence(
  value: StrategicHumanEvidenceInput,
): StrategicHumanEvidenceInput {
  const output: StrategicHumanEvidenceInput = {};
  for (const definition of STRATEGIC_EVIDENCE_DEFINITIONS) {
    const module = value[definition.moduleId];
    if (!module) continue;
    const evidence = Object.fromEntries(
      definition.requiredFields
        .map((field) => [
          field,
          (module.evidence[field] || [])
            .map((item) => item.trim())
            .filter(Boolean)
            .slice(0, 100),
        ] as const)
        .filter(([, items]) => items.length > 0),
    );
    const hasContent = Object.keys(evidence).length > 0
      || module.reviewer.trim()
      || module.observed_at.trim()
      || module.source_reference.trim()
      || module.excluded
      || module.exclusion_rationale.trim();
    if (!hasContent) continue;
    output[definition.moduleId] = {
      evidence,
      reviewer: module.reviewer.trim(),
      observed_at: module.observed_at.trim(),
      source_reference: module.source_reference.trim(),
      excluded: module.excluded,
      exclusion_rationale: module.exclusion_rationale.trim(),
    };
  }
  return output;
}
