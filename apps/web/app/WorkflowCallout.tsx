"use client";

import {usePathname} from "next/navigation";

type WorkflowCopy = {
  eyebrow: string;
  title: string;
  summary: string;
  steps: Array<{number: string; title: string; detail: string}>;
  runLabel: string;
  reviewLabel: string;
  boundary: string;
};

const ENGLISH_COPY: WorkflowCopy = {
  eyebrow: "Assessment workflow",
  title: "From repository evidence to an approval-ready report",
  summary: "One guided workspace keeps the assessment, evidence package, report, and final human decision connected to the same immutable repository snapshot.",
  steps: [
    {
      number: "01",
      title: "Run",
      detail: "Create an authorized assessment engagement and capture the exact repository state.",
    },
    {
      number: "02",
      title: "Verify",
      detail: "Review exact-commit evidence, scanner dispositions, limitations, and cross-format report consistency.",
    },
    {
      number: "03",
      title: "Approve",
      detail: "Use Final Review to accept the exact report package. NICO never authorizes client delivery automatically.",
    },
  ],
  runLabel: "Create an engagement",
  reviewLabel: "Open Final Review",
  boundary: "Human review required · Client delivery remains blocked until the exact report and evidence snapshot are approved.",
};

const SPANISH_COPY: WorkflowCopy = {
  eyebrow: "Flujo de evaluación",
  title: "De la evidencia del repositorio a un informe listo para aprobación",
  summary: "Un espacio guiado mantiene la evaluación, la evidencia, el informe y la decisión humana vinculados a la misma instantánea inmutable.",
  steps: [
    {
      number: "01",
      title: "Iniciar",
      detail: "Crea un encargo autorizado y captura el estado exacto del repositorio.",
    },
    {
      number: "02",
      title: "Verificar",
      detail: "Revisa evidencia del commit exacto, analizadores, limitaciones y consistencia entre formatos.",
    },
    {
      number: "03",
      title: "Aprobar",
      detail: "Usa Revisión final para aceptar el paquete exacto. NICO nunca autoriza automáticamente la entrega.",
    },
  ],
  runLabel: "Crear un encargo",
  reviewLabel: "Abrir Revisión final",
  boundary: "Revisión humana obligatoria · La entrega permanece bloqueada hasta aprobar el informe exacto y su evidencia.",
};

export default function WorkflowCallout() {
  const pathname = usePathname();
  if (pathname.startsWith("/assessment") || pathname.startsWith("/es/assessment")) return null;

  const spanish = pathname.startsWith("/es");
  const copy = spanish ? SPANISH_COPY : ENGLISH_COPY;
  const assessmentHref = spanish
    ? "/es/assessment?tier=comprehensive#assessment"
    : "/assessment?tier=comprehensive#assessment";

  return (
    <section
      className="workflow-banner"
      aria-labelledby="workflow-banner-title"
      lang={spanish ? "es-MX" : undefined}
    >
      <div className="workflow-banner-intro">
        <span className="workflow-banner-eyebrow">{copy.eyebrow}</span>
        <h2 id="workflow-banner-title">{copy.title}</h2>
        <p>{copy.summary}</p>
      </div>

      <ol className="workflow-banner-steps">
        {copy.steps.map((step) => (
          <li key={step.number}>
            <span className="workflow-step-number" aria-hidden="true">{step.number}</span>
            <div>
              <strong>{step.title}</strong>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="workflow-banner-footer">
        <div className="workflow-banner-actions">
          <a className="workflow-action-primary" href={assessmentHref}>{copy.runLabel}</a>
          <a className="workflow-action-secondary" href="/operations/final-review">{copy.reviewLabel}</a>
        </div>
        <p className="workflow-boundary">{copy.boundary}</p>
      </div>
    </section>
  );
}
