"use client";

import {usePathname} from "next/navigation";

export default function WorkflowCallout() {
  const pathname = usePathname();

  if (pathname.startsWith("/es-mx")) {
    return (
      <div className="full-run-callout" role="status" lang="es-MX">
        <b>Flujo de evaluación:</b> Inicie Express, Mid o Full desde la <a href="/assessment?tier=express#assessment">página unificada de evaluación</a>. Una sola acción de ejecución completa todas las etapas automatizadas disponibles para el nivel seleccionado. Mid y Full continúan con evidencia del repositorio, escáneres, puntuación y preparación del reporte, y después se detienen para la revisión humana obligatoria. NICO nunca aprueba hallazgos ni crea entregas para clientes automáticamente. La aprobación crea un artefacto aprobado independiente, pero no crea un enlace de entrega al cliente. Las descargas del cliente requieren confirmación y generan recibos vinculados a la integridad. Los operadores pueden verificar despliegue, disponibilidad, carga de trabajo, incidentes, evidencia de respaldo y restauración, y alertas en el centro de control de <a href="/operations">Operaciones</a>, y revisar trabajo interrumpido de escáneres en <a href="/operations/recovery">Recuperación</a>. <b>Flujo de retainer:</b> Ejecute evidencia continua del repositorio, flujo de trabajo, versiones, pendientes y bloqueadores mediante <a href="/retainer-ops">Retainer Ops</a>; solo se captura manualmente el contexto comercial que GitHub no puede demostrar.
      </div>
    );
  }

  return (
    <div className="full-run-callout" role="status">
      <b>Assessment workflow:</b> Start Express, Mid, or Full from the <a href="/assessment?tier=express#assessment">unified assessment page</a>. One Run action completes every automated stage available for the selected tier. Mid and Full continue through repository evidence, scanners, scoring, and report preparation, then stop at required human review. NICO never approves findings or creates client delivery automatically. Approval creates a separate approved artifact but does not create a client delivery link. Client downloads require acknowledgement and create integrity-bound receipts. Operators can verify deployment, readiness, workload, incidents, backup/restore evidence, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>. <b>Retainer workflow:</b> Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually.
    </div>
  );
}
