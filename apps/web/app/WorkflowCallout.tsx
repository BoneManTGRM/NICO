"use client";

import type {ReactNode} from "react";
import {usePathname} from "next/navigation";

export default function WorkflowCallout({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const spanish = pathname.startsWith("/es");

  if (spanish) {
    return (
      <div className="full-run-callout" role="status" lang="es-MX">
        <b>Flujo de evaluación:</b> inicia Express o Integral desde el <a href="/es/assessment?tier=express#assessment">espacio de evaluaciones</a>. Express proporciona una línea base técnica rápida vinculada a evidencia. Integral captura un commit inmutable y continúa la misma ejecución por la evidencia del repositorio, los analizadores, los módulos técnicos y de contexto comercial, la generación del informe y la revisión humana obligatoria. NICO nunca aprueba hallazgos ni autoriza automáticamente una entrega al cliente. Los operadores pueden verificar el despliegue, la disponibilidad, la carga de trabajo, los incidentes, la evidencia de respaldo y restauración, y las alertas en el centro de control de <a href="/operations?lang=es-MX">Operaciones</a>, además de revisar ejecuciones interrumpidas de los analizadores en <a href="/operations/recovery?lang=es-MX">Recuperación</a>. <b>Flujo de servicio continuo:</b> procesa evidencia recurrente del repositorio, flujos de trabajo, publicaciones, pendientes y bloqueadores mediante <a href="/retainer-ops?lang=es-MX">Operaciones continuas</a>; únicamente se captura de forma manual el contexto comercial que GitHub no puede demostrar.
      </div>
    );
  }

  return children;
}
