"use client";

import type {ReactNode} from "react";
import {usePathname} from "next/navigation";

export default function WorkflowCallout({children}: {children: ReactNode}) {
  const pathname = usePathname();

  if (pathname.startsWith("/es-mx")) {
    return (
      <div className="full-run-callout" role="status" lang="es-MX">
        <b>Flujo de evaluación:</b> Inicie Express, Mid o Full desde la <a href="/assessment?tier=express#assessment">página unificada de evaluación</a>. Una sola acción de ejecución completa todas las etapas automatizadas disponibles para el nivel seleccionado. Mid y Full continúan con evidencia del repositorio, escáneres, puntuación y preparación del reporte, y después se detienen para la revisión humana obligatoria. NICO nunca aprueba hallazgos ni crea entregas para clientes automáticamente. La aprobación crea un artefacto aprobado independiente, pero no crea un enlace de entrega al cliente. Las descargas del cliente requieren confirmación y generan recibos vinculados a la integridad. Los operadores pueden verificar despliegue, disponibilidad, carga de trabajo, incidentes, evidencia de respaldo y restauración, y alertas en el centro de control de <a href="/operations">Operaciones</a>, y revisar trabajo interrumpido de escáneres en <a href="/operations/recovery">Recuperación</a>. <b>Flujo de retainer:</b> Ejecute evidencia continua del repositorio, flujo de trabajo, versiones, pendientes y bloqueadores mediante <a href="/retainer-ops">Retainer Ops</a>; solo se captura manualmente el contexto comercial que GitHub no puede demostrar.
      </div>
    );
  }

  return children;
}
