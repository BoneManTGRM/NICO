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

export const STRATEGIC_EVIDENCE_DEFINITIONS: StrategicEvidenceDefinition[] = [
  {
    moduleId: "functional_qa",
    label: {en: "Functional QA", "es-MX": "QA funcional"},
    description: {
      en: "Executed user journeys, expected results, and observed outcomes.",
      "es-MX": "Recorridos de usuario ejecutados, resultados esperados y resultados observados.",
    },
    requiredFields: ["test_cases", "observed_results"],
  },
  {
    moduleId: "platform_parity",
    label: {en: "Platform parity", "es-MX": "Paridad de plataformas"},
    description: {
      en: "Browser, device, operating-system, web, and native parity evidence.",
      "es-MX": "Evidencia de paridad entre navegadores, dispositivos, sistemas operativos, web y aplicaciones nativas.",
    },
    requiredFields: ["platform_matrix", "observed_differences"],
  },
  {
    moduleId: "accessibility_ux",
    label: {en: "Accessibility and UX", "es-MX": "Accesibilidad y experiencia de usuario"},
    description: {
      en: "Keyboard, screen-reader, contrast, task-completion, and recovery observations.",
      "es-MX": "Observaciones de teclado, lector de pantalla, contraste, finalización de tareas y recuperación.",
    },
    requiredFields: ["scenarios", "observations"],
  },
  {
    moduleId: "stakeholder_context",
    label: {en: "Stakeholder context", "es-MX": "Contexto de las partes interesadas"},
    description: {
      en: "Objectives, pain points, constraints, desired state, and decision priorities.",
      "es-MX": "Objetivos, problemas, restricciones, estado deseado y prioridades de decisión.",
    },
    requiredFields: ["objectives", "constraints"],
  },
  {
    moduleId: "incident_history",
    label: {en: "Incident history", "es-MX": "Historial de incidentes"},
    description: {
      en: "Material incidents, customer impact, response, recovery, and recurrence evidence.",
      "es-MX": "Incidentes importantes, impacto al cliente, respuesta, recuperación y evidencia de recurrencia.",
    },
    requiredFields: ["incidents", "lessons_learned"],
  },
  {
    moduleId: "product_objectives",
    label: {en: "Product objectives", "es-MX": "Objetivos del producto"},
    description: {
      en: "Product goals, success measures, release intent, and business outcomes.",
      "es-MX": "Metas del producto, medidas de éxito, intención de lanzamiento y resultados de negocio.",
    },
    requiredFields: ["goals", "success_measures"],
  },
  {
    moduleId: "release_constraints",
    label: {en: "Release constraints", "es-MX": "Restricciones de lanzamiento"},
    description: {
      en: "Deadlines, dependencies, maintenance windows, contractual dates, and operational limits.",
      "es-MX": "Fechas límite, dependencias, ventanas de mantenimiento, fechas contractuales y límites operativos.",
    },
    requiredFields: ["deadlines", "constraints"],
  },
  {
    moduleId: "compliance_requirements",
    label: {en: "Compliance and contractual requirements", "es-MX": "Requisitos normativos y contractuales"},
    description: {
      en: "Applicable obligations, customer commitments, control expectations, and evidence owners.",
      "es-MX": "Obligaciones aplicables, compromisos con clientes, expectativas de control y responsables de evidencia.",
    },
    requiredFields: ["requirements", "evidence_expectations"],
  },
  {
    moduleId: "budget_staffing",
    label: {en: "Budget and staffing", "es-MX": "Presupuesto y personal"},
    description: {
      en: "Available roles, capacity, budget boundaries, hiring limits, and delivery assumptions.",
      "es-MX": "Roles disponibles, capacidad, límites presupuestarios, restricciones de contratación y supuestos de entrega.",
    },
    requiredFields: ["staffing", "constraints"],
  },
  {
    moduleId: "accepted_risks",
    label: {en: "Accepted risks and decisions", "es-MX": "Riesgos y decisiones aceptados"},
    description: {
      en: "Explicit risk acceptance, owner, expiration, rationale, and approval boundary.",
      "es-MX": "Aceptación explícita de riesgos, responsable, vencimiento, justificación y límite de aprobación.",
    },
    requiredFields: ["decisions", "approval_boundaries"],
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
  const fieldsComplete = definition.requiredFields.every((field) => (value.evidence[field] || []).length > 0);
  const metadataComplete = Boolean(value.reviewer.trim() && value.observed_at.trim() && value.source_reference.trim());
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
        .map((field) => [field, (module.evidence[field] || []).map((item) => item.trim()).filter(Boolean).slice(0, 100)] as const)
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
