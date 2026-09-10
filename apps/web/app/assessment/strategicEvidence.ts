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
  fields?: string[];
};

// The exact ten module IDs and baseline required fields mirror
// nico.decision_grade_human_evidence_v1.MODULE_DEFINITIONS. Phase 3 may expose
// additional retained evidence fields without mutating that historical
// completeness/hash contract.
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
    label: {en: "Stakeholder, engagement, and authorization context", "es-MX": "Contexto de interesados, encargo y autorización"},
    description: {
      en: "Stakeholder objectives and constraints are optional engagement evidence. For actual client work, also supply the access method, primary technical contact, and authorized scope. Leave client/project blank for a clearly internal assessment.",
      "es-MX": "Los objetivos y restricciones de interesados son evidencia opcional del encargo. Para trabajo real de cliente, también proporcione el método de acceso, contacto técnico principal y alcance autorizado. Deje cliente/proyecto vacíos para una evaluación interna claramente marcada.",
    },
    requiredFields: ["objectives", "constraints"],
    fields: ["objectives", "constraints", "access_method", "primary_technical_contact", "authorized_scope"],
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
    label: {en: "Requirements, specifications, ADRs, and acceptance criteria", "es-MX": "Requisitos, especificaciones, ADR y criterios de aceptación"},
    description: {
      en: "Requirements or commitments supplied by an authorized source. State whether the supplied source is authoritative, approved, contractual, draft, or otherwise unverified. NICO maps evidence but never invents obligations.",
      "es-MX": "Requisitos o compromisos proporcionados por una fuente autorizada. Indique si la fuente es autoritativa, aprobada, contractual, borrador o no verificada. NICO relaciona evidencia pero nunca inventa obligaciones.",
    },
    requiredFields: ["requirements"],
    fields: ["requirements", "authority_status"],
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

export function evidenceFields(definition: StrategicEvidenceDefinition): string[] {
  return definition.fields || definition.requiredFields;
}

export const CLIENT_ENGAGEMENT_FIELDS = new Set([
  "access_method",
  "primary_technical_contact",
  "authorized_scope",
]);

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
      evidenceFields(definition)
        .map((field) => [
          field,
          CLIENT_ENGAGEMENT_FIELDS.has(field)
            ? (module.evidence[field] || [])
              .filter((item) => item.trim())
              .slice(0, 1)
            : (module.evidence[field] || [])
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
