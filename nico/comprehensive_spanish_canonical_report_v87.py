from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader

from nico.comprehensive_report_package import _markdown, _pdf, _semantic_html
from nico.comprehensive_report_spanish_text_v51 import ES_EXACT
from nico.comprehensive_spanish_presentation_parity_v1 import (
    _ES_EXTRA_EXACT,
    _ES_PHRASES,
    _safe_replace,
)

VERSION = "nico.comprehensive-spanish-canonical-report.v87"

# Use the same visible worksheet titles as the English-derived review contract.
# Downstream compaction identifies those semantic sections by their localized
# titles; alternate synonyms would leave duplicate stage blocks/pages in Spanish.
_CANONICAL_PARITY_EXACT = {
    "Comprehensive": "Integral",
    "DRAFT": "BORRADOR AUTOMATIZADO",
    "Page": "Página",
    "Functional QA": "QA funcional",
    "Platform Parity": "Paridad de plataformas",
    "Stakeholder and Business Alignment": "Alineación comercial y de partes interesadas",
    "Target complexity is at most 30": "La complejidad objetivo es de 30 como máximo",
    "Workflow outcome classes:": (
        "Clases de resultados de los flujos de trabajo: no se conservaron "
        "resultados clasificados."
    ),
    "JavaScript and TypeScript complexity uses a bounded lexical heuristic because a full parser artifact was not attached; those module-level values are lower-confidence than Python AST metrics.": (
        "La complejidad de JavaScript y TypeScript utiliza una heurística léxica "
        "acotada porque no se adjuntó un artefacto de analizador completo; esos "
        "valores a nivel de módulo tienen menor confianza que las métricas del AST "
        "de Python."
    ),
    "JavaScript and TypeScript complexity uses bounded function-level lexical extraction rather than a full language parser; dynamic syntax and parser-level semantics remain lower-confidence than Python AST metrics.": (
        "La complejidad de JavaScript y TypeScript utiliza extracción léxica acotada "
        "a nivel de función en lugar de un analizador completo del lenguaje; la "
        "sintaxis dinámica y la semántica a nivel de analizador siguen teniendo menor "
        "confianza que las métricas del AST de Python."
    ),
    "Scanner evidence is not client-ready until every required scanner completes and every redacted raw artifact is retained.": (
        "La evidencia de analizadores no está lista para el cliente hasta que se "
        "completen todos los analizadores requeridos y se conserve cada artefacto "
        "sin procesar redactado."
    ),
    "No workflow files were present in the captured repository snapshot.": (
        "No había archivos de flujos de trabajo en la instantánea capturada del "
        "repositorio."
    ),
    "Captured-commit collection reached its bounded runtime; remaining files are unavailable for this run.": (
        "La recopilación del commit capturado alcanzó su tiempo de ejecución "
        "acotado; los archivos restantes no están disponibles para esta ejecución."
    ),
    "No eligible source files were present in the authorized GitHub text-file sample.": (
        "No había archivos de código fuente elegibles en la muestra autorizada de "
        "archivos de texto de GitHub."
    ),
    "OSV lookup skipped because no exact dependency versions were available from the inspected manifests.": (
        "Se omitió la consulta a OSV porque no había versiones exactas de "
        "dependencias disponibles en los manifiestos inspeccionados."
    ),
    "OSV lookup skipped because no exact normalized dependency versions were available from the inspected manifests.": (
        "Se omitió la consulta a OSV porque no había versiones exactas normalizadas "
        "de dependencias disponibles en los manifiestos inspeccionados."
    ),
    "OSV lookup did not complete within the bounded dependency-review window.": (
        "La consulta a OSV no se completó dentro de la ventana acotada de revisión "
        "de dependencias."
    ),
    "OSV lookup returned a non-JSON response.": (
        "La consulta a OSV devolvió una respuesta que no era JSON."
    ),
    "GitHub deployment evidence was returned without a deployment list.": (
        "La evidencia de despliegues de GitHub se devolvió sin una lista de "
        "despliegues."
    ),
    "Snapshot-bound repository evidence requires an attached snapshot with matching run and repository identity.": (
        "La evidencia del repositorio vinculada a la instantánea requiere una "
        "instantánea adjunta cuya identidad de ejecución y repositorio coincida."
    ),
    "TypeScript compiler AST evidence was unavailable for this run; JavaScript and TypeScript values use bounded lexical fallback and remain review-limited.": (
        "La evidencia del AST del compilador de TypeScript no estaba disponible para "
        "esta ejecución; los valores de JavaScript y TypeScript utilizan una "
        "alternativa léxica acotada y siguen limitados por revisión."
    ),
    "No eligible first-party source files were present in the exact-SHA source profile.": (
        "No había archivos de código fuente propios elegibles en el perfil de código "
        "fuente del SHA exacto."
    ),
    "Exact-SHA source archive was unavailable because the snapshot commit was missing.": (
        "El archivo de código fuente del SHA exacto no estaba disponible porque "
        "faltaba el commit de la instantánea."
    ),
    "All observed required scanners in this control completed with retained exact-SHA artifacts.": (
        "Todos los analizadores requeridos observados en este control se completaron "
        "con artefactos conservados para el SHA exacto."
    ),
    "All repository file evidence and scanner execution for this run must use this exact commit SHA or be marked unavailable.": (
        "Toda la evidencia de archivos del repositorio y la ejecución de analizadores "
        "para esta ejecución deben utilizar el SHA exacto de este commit o marcarse "
        "como no disponibles."
    ),
}

_STAGE_PHRASE_ES = {
    "authorization and scope": "autorización y alcance",
    "immutable repository snapshot": "instantánea inmutable del repositorio",
    "repository and delivery evidence": "evidencia del repositorio y de entrega",
    "dependency security static analysis": "análisis de dependencias, seguridad y análisis estático",
    "ci cd architecture complexity velocity": "CI/CD, arquitectura, complejidad y velocidad",
    "evidence reconciliation and scoring": "conciliación y puntuación de evidencia",
    "decision report generation": "generación del informe para decisiones",
    "deep scanner triage": "triaje profundo de analizadores",
    "functional qa": "QA funcional",
    "platform parity": "paridad de plataformas",
    "deployment and infrastructure": "despliegue e infraestructura",
    "architecture and data flow": "arquitectura y flujo de datos",
    "developer delivery process": "proceso de entrega de desarrollo",
    "stakeholder and business alignment": "alineación comercial y de partes interesadas",
    "requirements traceability": "trazabilidad de requisitos",
    "historical trends and change failure": "tendencias históricas y fallos de cambio",
    "six month roadmap": "hoja de ruta de seis meses",
    "staffing sequencing and cost": "personal, secuencia y costo",
    "risk reduction and executive briefing": "reducción de riesgo y resumen ejecutivo",
}

# Machine evidence is immutable across locales. Everything else in the canonical
# report projection is renderer-owned presentation copy and may be localized.
_PROTECTED_FIELDS = {
    "artifact_type",
    "canonical_state",
    "candidate_id",
    "candidate_state",
    "code",
    "client_name",
    "commit_sha",
    "customer_name",
    "customer_id",
    "evidence_ledger_id",
    "exact_source",
    "filename",
    "finding_id",
    "generated_at",
    "generation_timestamp",
    "id",
    "disposition",
    "execution_status",
    "location",
    "module",
    "package",
    "package_name",
    "path",
    "problematic_code",
    "project_id",
    "project_name",
    "primary_technical_contact",
    "access_method",
    "authorized_scope",
    "presented_status",
    "raw_output",
    "raw_payload",
    "repository",
    "rule_id",
    "run_id",
    "scanner_name",
    "schema_version",
    "section_id",
    "sha256",
    "source_path",
    "source_excerpt",
    "stage_id",
    "state",
    "status",
    "symbol",
    "test_id",
    "tool",
    "url",
    "version",
    "command",
    "function_or_component",
    "advisory_id",
}

# These values must remain byte-for-byte identical after the final presentation
# pass. Status/state values are intentionally excluded: their canonical values
# stay immutable in JSON, while their visible display labels are localized.
_POST_RENDER_PROTECTED_FIELDS = _PROTECTED_FIELDS - {
    "candidate_state",
    "canonical_state",
    "disposition",
    "execution_status",
    "presented_status",
    "state",
    "status",
}

_PRESENTATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED",
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
    ),
    (
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
    ),
    ("AUTOMATED DRAFT", "BORRADOR AUTOMATIZADO"),
    ("Primary technical contact", "Contacto técnico principal"),
    ("Project display name", "Nombre del proyecto"),
    ("Client display name", "Nombre del cliente"),
    ("Access method", "Método de acceso"),
    ("Authorized scope", "Alcance autorizado"),
    ("Not scored", "Sin puntuación"),
    ("Not supplied", "No proporcionado"),
    ("Product Engineering", "Ingeniería de producto"),
    ("Requires estimation", "Requiere estimación"),
    ("NICO Comprehensive Technical Assessment", "Evaluación Técnica Integral NICO"),
    ("Comprehensive Technical Assessment", "Evaluación Técnica Integral"),
    ("Priority Constraints and Decision Risks", "Restricciones prioritarias y riesgos de decisión"),
    ("Priority Constraints and Risks", "Restricciones prioritarias y riesgos"),
    ("Executive Decision Brief", "Resumen ejecutivo para decisiones"),
    ("Decision Boundary", "Límite de decisión"),
    ("Canonical Maturity Signal", "Señal canónica de madurez"),
    ("Canonical Technical Scorecard", "Cuadro de puntuación técnica"),
    ("Technical Scorecard", "Cuadro de puntuación técnica"),
    ("Canonical scoring", "Puntuación canónica"),
    ("Code Audit", "Auditoría de código"),
    ("Dependency / Library Ecosystem", "Ecosistema de dependencias y bibliotecas"),
    ("Secrets Exposure Review", "Revisión de exposición de secretos"),
    ("Static Analysis", "Análisis estático"),
    ("CI/CD Analysis", "Análisis de CI/CD"),
    ("Architecture & Technical Debt", "Arquitectura y deuda técnica"),
    ("Velocity / Complexity", "Velocidad y complejidad"),
    ("Dynamic execution pattern", "Patrón de ejecución dinámica"),
    ("Reduce complexity in", "Reducir la complejidad en"),
    (
        "Confirm the test fixture is intentional.",
        "Confirmar que el fixture de prueba sea intencional.",
    ),
    ("verified", "verificada"),
    ("1-2 days", "1-2 días"),
    (
        "The client disables certificate verification.",
        "El cliente deshabilita la verificación del certificado.",
    ),
    (
        "Remove verify=False and use the approved trust store.",
        "Eliminar verify=False y usar el almacén de confianza aprobado.",
    ),
    (
        "Run Bandit against the same immutable revision.",
        "Ejecutar Bandit contra la misma revisión inmutable.",
    ),
    (
        "Run Bandit contra la misma revisión inmutable.",
        "Ejecutar Bandit contra la misma revisión inmutable.",
    ),
    (
        "Restore the prior client configuration if compatibility fails.",
        "Restaurar la configuración anterior del cliente si falla la compatibilidad.",
    ),
    (
        "B501 is absent from the exact-SHA scanner output.",
        "B501 no aparece en la salida del analizador para el SHA exacto.",
    ),
    (
        "B501 is absent from the SHA exacto scanner output.",
        "B501 no aparece en la salida del analizador para el SHA exacto.",
    ),
    ("Evidence Foundation", "Fundamento de evidencia"),
    ("Deep Technical Diligence", "Diligencia técnica profunda"),
    ("Business and Delivery Context", "Contexto comercial y de entrega"),
    ("Roadmap, Resourcing, and Decision", "Hoja de ruta, recursos y decisión"),
    ("Integrity and Acceptance", "Integridad y aceptación"),
    ("Additional Recorded Stages", "Etapas registradas adicionales"),
    ("Assessment-Wide Limitations", "Limitaciones generales de la evaluación"),
    ("Human Review Checklist", "Lista de verificación para revisión humana"),
    ("Human Review and Acceptance Gate", "Puerta de revisión y aceptación humana"),
    ("Evidence Appendix", "Apéndice de evidencia"),
    ("Evidence Limitations", "Limitaciones de evidencia"),
    ("Unavailable or Limited Evidence", "Evidencia no disponible o limitada"),
    ("Retained Evidence", "Evidencia conservada"),
    ("Delivery Status", "Estado de entrega"),
    ("Presented score", "Puntuación presentada"),
    ("Evidence readiness", "Preparación de la evidencia"),
    ("Immutable commit SHA", "SHA del commit inmutable"),
    ("Evidence ledger ID", "ID del libro mayor de evidencia"),
    ("Customer scope", "Alcance del cliente"),
    ("Project scope", "Alcance del proyecto"),
    ("Service ID", "ID del servicio"),
    ("Stage ID", "ID de etapa"),
    ("Run ID", "ID de ejecución"),
    ("Immutable commit", "Commit inmutable"),
    ("Generated", "Generado"),
    ("Repository", "Repositorio"),
    ("Service", "Servicio"),
    ("Customer", "Cliente"),
    ("Project", "Proyecto"),
    ("Maturity", "Madurez"),
    ("Control", "Control"),
    ("Status", "Estado"),
    ("Score", "Puntuación"),
    ("Summary", "Resumen"),
    ("Level", "Nivel"),
    ("Findings", "Hallazgos"),
    ("Evidence", "Evidencia"),
    (
        "NICO generated an automated Comprehensive Technical Assessment draft for",
        "NICO generó un borrador automatizado de Evaluación Técnica Integral para",
    ),
    (
        "NICO completed a native Comprehensive Technical Assessment for",
        "NICO completó una Evaluación Técnica Integral nativa para",
    ),
    (
        "NICO generated an automated Evaluación Técnica Integral draft for",
        "NICO generó un borrador automatizado de Evaluación Técnica Integral para",
    ),
    ("at immutable commit", "en el commit inmutable"),
    (
        "The evidence-bound maturity signal is",
        "La señal de madurez basada en evidencia es",
    ),
    (
        "The basado en evidencia maturity signal is",
        "La señal de madurez basada en evidencia es",
    ),
    (
        "No automated stage represented in this package has a retained terminal execution failure.",
        "Ninguna etapa automatizada representada en este paquete conserva un fallo terminal de ejecución.",
    ),
    (
        "Every automated stage represented in this package completed without a terminal execution failure.",
        "Todas las etapas automatizadas representadas en este paquete se completaron sin un fallo terminal de ejecución.",
    ),
    (
        "The package is review-gated: automated evidence and recommendations are not client approval or delivery authorization.",
        "El paquete está sujeto a revisión: la evidencia y las recomendaciones automatizadas no constituyen aprobación del cliente ni autorización de entrega.",
    ),
    (
        "The package is a review-gated draft: automated evidence and recommendations are not client approval or delivery authorization.",
        "El paquete es un borrador sujeto a revisión: la evidencia y las recomendaciones automatizadas no constituyen aprobación del cliente ni autorización de entrega.",
    ),
    (
        "The package is review-gated: automated evidence and recommendations are not human approval or client-delivery authorization.",
        "El paquete está sujeto a revisión: la evidencia y las recomendaciones automatizadas no constituyen aprobación humana ni autorización de entrega al cliente.",
    ),
    (
        "section(s) disclose unavailable, limited, framework-only, or stakeholder-dependent evidence.",
        "declaran evidencia no disponible, limitada, de marco o dependiente de las partes interesadas.",
    ),
    ("client-review", "sección(es) de revisión del cliente"),
    ("No automated stage represented", "Ninguna etapa automatizada representada"),
    (
        "in this package has a retained terminal execution failure.",
        "en este paquete conserva un fallo terminal de ejecución.",
    ),
    (
        "The package is review-gated: automated evidence and",
        "El paquete está sujeto a revisión: la evidencia y las recomendaciones automatizadas",
    ),
    (
        "recommendations are not human approval or client-delivery authorization.",
        "no constituyen aprobación humana ni autorización de entrega al cliente.",
    ),
    (
        "recommendations are not client approval or delivery authorization.",
        "no constituyen aprobación del cliente ni autorización de entrega.",
    ),
    (
        "The report is an evidence-bound draft. NICO has not approved findings, accepted business assumptions, or authorized delivery. Missing evidence remains visible and constrains conclusions.",
        "El informe es un borrador basado en evidencia. NICO no ha aprobado hallazgos, aceptado supuestos comerciales ni autorizado la entrega. La evidencia faltante permanece visible y limita las conclusiones.",
    ),
    (
        "The report is an evidence-bound draft.",
        "El informe es un borrador basado en evidencia.",
    ),
    (
        "The report is an basado en evidencia draft.",
        "El informe es un borrador basado en evidencia.",
    ),
    (
        "NICO has not approved findings, accepted business assumptions, or authorized delivery.",
        "NICO no ha aprobado hallazgos, aceptado supuestos comerciales ni autorizado la entrega.",
    ),
    (
        "Missing evidence remains visible and constrains conclusions.",
        "La evidencia faltante permanece visible y limita las conclusiones.",
    ),
    (
        "Missing evidencia remains visible and constrains conclusions.",
        "La evidencia faltante permanece visible y limita las conclusiones.",
    ),
    (
        "Human review is required. Client delivery is blocked. Missing evidence is disclosed and is never converted into a passing claim.",
        "Se requiere revisión humana. La entrega al cliente está bloqueada. La evidencia faltante se declara y nunca se convierte en una afirmación aprobatoria.",
    ),
    (
        "The appendix preserves full bounded stage evidence for the immutable run. It is intentionally separate from the decision-oriented body.",
        "El apéndice conserva la evidencia completa y acotada de las etapas de la ejecución inmutable. Se mantiene separado intencionalmente del cuerpo orientado a decisiones.",
    ),
    (
        "The appendix preserves full bounded stage evidence for the immutable run.",
        "El apéndice conserva la evidencia completa y acotada de las etapas de la ejecución inmutable.",
    ),
    (
        "It is intentionally separate from the decision-oriented body.",
        "Se mantiene separado intencionalmente del cuerpo orientado a decisiones.",
    ),
    (
        "The automated assessment is complete only as a draft. The following decisions remain human responsibilities:",
        "La evaluación automatizada está completa únicamente como borrador. Las siguientes decisiones siguen siendo responsabilidad humana:",
    ),
    (
        "Verify the exact repository, run, commit, evidence ledger, customer, and project identities.",
        "Verificar las identidades exactas del repositorio, la ejecución, el commit, el libro mayor de evidencia, el cliente y el proyecto.",
    ),
    (
        "Triage every failed, timed-out, unavailable, and review-required scanner result.",
        "Revisar cada resultado de analizador fallido, agotado, no disponible o que requiera revisión.",
    ),
    (
        "Validate business context, requirements, roadmap, staffing, sequencing, and cost assumptions.",
        "Validar el contexto comercial, los requisitos, la hoja de ruta y los supuestos de personal, secuencia y costo.",
    ),
    (
        "Confirm Markdown, HTML, JSON, and PDF show the same status and score truth.",
        "Confirmar que Markdown, HTML, JSON y PDF muestren la misma verdad de estado y puntuación.",
    ),
    (
        "Approve or reject the immutable report package before creating any delivery access.",
        "Aprobar o rechazar el paquete inmutable del informe antes de crear cualquier acceso de entrega.",
    ),
    (
        "Verify repository, run, commit, ledger, customer, and project identities.",
        "Verificar las identidades del repositorio, la ejecución, el commit, el libro mayor, el cliente y el proyecto.",
    ),
    (
        "Review every failed, timed-out, unavailable, and triage-required analyzer result.",
        "Revisar cada resultado de analizador fallido, agotado, no disponible o que requiera triaje.",
    ),
    (
        "Confirm the scorecard matches the evidence and all report formats.",
        "Confirmar que el cuadro de puntuación coincida con la evidencia y todos los formatos del informe.",
    ),
    (
        "Validate business context, requirements, roadmap, staffing, and cost assumptions.",
        "Validar el contexto comercial, los requisitos, la hoja de ruta y los supuestos de personal y costo.",
    ),
    (
        "Approve or reject the exact immutable report package before any client delivery.",
        "Aprobar o rechazar el paquete inmutable exacto del informe antes de cualquier entrega al cliente.",
    ),
    (
        "The automated executive briefing and bounded priority register are complete for review; finding acceptance, residual-risk ownership, remediation commitment, and delivery authorization remain pending human disposition.",
        "El resumen ejecutivo automatizado y el registro acotado de prioridades están completos para revisión; la aceptación de hallazgos, la responsabilidad del riesgo residual, el compromiso de remediación y la autorización de entrega siguen pendientes de disposición humana.",
    ),
    (
        "CI/CD configuration maturity, current operational readiness, required-check health, and historical workflow outcomes are separate evidence concepts.",
        "La madurez de la configuración de CI/CD, la preparación operativa actual, la salud de las verificaciones requeridas y los resultados históricos de los flujos de trabajo son conceptos de evidencia separados.",
    ),
    (
        "The core decision-report artifacts were generated from synchronized canonical score truth and retained for final human review.",
        "Los artefactos principales del informe para decisiones se generaron a partir de la verdad sincronizada de la puntuación canónica y se conservaron para la revisión humana final.",
    ),
    (
        "Stakeholder interviews were not supplied and remain a human-context boundary.",
        "No se aportaron entrevistas con las partes interesadas y estas siguen siendo un límite de contexto humano.",
    ),
    (
        "Canonical technical evidence produced a Senior maturity signal.",
        "La evidencia técnica canónica produjo una señal de madurez Senior.",
    ),
    (
        "Canonical evidence is available.",
        "La evidencia canónica está disponible.",
    ),
    (
        "Exact-SHA first-party source archive when available; tests, generated, distribution, dependency, vendor, and minified paths are excluded.",
        "Archivo de código fuente propio del SHA exacto cuando está disponible; se excluyen las rutas de pruebas, código generado, distribución, dependencias, proveedores y archivos minificados.",
    ),
    (
        "Ownership or explicit authorization and the defensive read-only scope were confirmed for this exact Comprehensive run.",
        "Se confirmaron la propiedad o la autorización explícita y el alcance defensivo de solo lectura para esta ejecución integral exacta.",
    ),
    (
        "Score effect: assurance-only while authorized human disposition remains pending; NICO automated technical triage is complete.",
        "Efecto en la puntuación: solo aseguramiento mientras la disposición humana autorizada siga pendiente; el triaje técnico automatizado de NICO está completo.",
    ),
    (
        "Prior proposed dispositions may be retained only within the same assessment subject; human approval is never carried forward.",
        "Las disposiciones propuestas anteriormente solo pueden conservarse dentro del mismo sujeto de evaluación; la aprobación humana nunca se transfiere.",
    ),
    (
        "The authorized repository was bound to one immutable commit before evidence collection.",
        "El repositorio autorizado se vinculó a un único commit inmutable antes de recopilar la evidencia.",
    ),
    (
        "Exact-commit repository, dependency, architecture, workflow, activity, and complexity evidence were attached.",
        "Se adjuntó evidencia del repositorio, las dependencias, la arquitectura, los flujos de trabajo, la actividad y la complejidad correspondiente al commit exacto.",
    ),
    (
        "Dependency, static-analysis, secret, TypeScript, and history-aware scanner output was verified against the immutable commit.",
        "Los resultados de los analizadores de dependencias, análisis estático, secretos, TypeScript y revisión del historial se verificaron contra el commit inmutable.",
    ),
    (
        "CI/CD, architecture, source footprint, complexity, ownership, churn, and delivery velocity were analyzed from snapshot-bound and separately labeled historical evidence.",
        "CI/CD, la arquitectura, la huella del código fuente, la complejidad, la propiedad, la rotación del código y la velocidad de entrega se analizaron con evidencia vinculada a la instantánea y evidencia histórica etiquetada por separado.",
    ),
    (
        "The CI/CD architecture, source footprint, release gates, deployment topology, and environment protections were verified from repository evidence.",
        "La arquitectura de CI/CD, la huella del código fuente, las puertas de publicación, la topología de despliegue y las protecciones del entorno se verificaron a partir de la evidencia del repositorio.",
    ),
    (
        "Functional QA evidence was assessed from test footprint and CI command configuration; runtime acceptance remains human-supplied evidence.",
        "La evidencia de QA funcional se evaluó a partir de la cobertura de pruebas y la configuración de comandos de CI; la aceptación en ejecución sigue dependiendo de evidencia aportada por personas.",
    ),
    (
        "Functional QA was reconstructed from available test, route, workflow, and runtime evidence.",
        "La QA funcional se reconstruyó a partir de la evidencia disponible de pruebas, rutas, flujos de trabajo y ejecución.",
    ),
    (
        "The modern scanner suite is executing against the exact immutable commit.",
        "El conjunto moderno de analizadores se está ejecutando contra el commit inmutable exacto.",
    ),
    (
        "Scanner output did not verify the immutable snapshot.",
        "Los resultados de los analizadores no verificaron la instantánea inmutable.",
    ),
    (
        "The immutable repository snapshot was unavailable.",
        "La instantánea inmutable del repositorio no estaba disponible.",
    ),
    (
        "Platform evidence was inventoried without claiming parity where runnable builds or native project evidence were unavailable.",
        "Se inventarió la evidencia de plataformas sin afirmar paridad cuando no había compilaciones ejecutables ni evidencia de proyectos nativos.",
    ),
    (
        "Deployment manifests, workflow deployment evidence, and runtime configuration controls were reviewed.",
        "Se revisaron los manifiestos de despliegue, la evidencia de despliegue de los flujos de trabajo y los controles de configuración de ejecución.",
    ),
    (
        "Architecture, top-level modules, deployment boundaries, source footprint, and measured complexity were synthesized into a data-flow review boundary.",
        "La arquitectura, los módulos de nivel superior, los límites de despliegue, la huella del código fuente y la complejidad medida se sintetizaron en un límite de revisión del flujo de datos.",
    ),
    (
        "Commit, pull-request, workflow, job, and deployment evidence were reviewed as bounded delivery-process history.",
        "La evidencia de commits, solicitudes de incorporación, flujos de trabajo, trabajos y despliegues se revisó como historial acotado del proceso de entrega.",
    ),
    (
        "Stakeholder and business alignment remains an explicit human-context boundary; NICO did not infer unprovided objectives or approvals.",
        "La alineación comercial y de las partes interesadas sigue siendo un límite explícito de contexto humano; NICO no infirió objetivos ni aprobaciones no aportados.",
    ),
    (
        "Repository documentation was searched for requirements, specifications, ADRs, roadmaps, and acceptance evidence.",
        "Se examinó la documentación del repositorio en busca de requisitos, especificaciones, ADR, hojas de ruta y evidencia de aceptación.",
    ),
    (
        "Historical change and failure signals were calculated only from bounded GitHub operational evidence observed through capture time.",
        "Las señales históricas de cambios y fallos se calcularon únicamente a partir de la evidencia operativa acotada de GitHub observada hasta el momento de la captura.",
    ),
    (
        "A six-month roadmap was sequenced from the lowest evidence-bound controls and explicit unavailable-evidence boundaries.",
        "Se secuenció una hoja de ruta de seis meses a partir de los controles con menor puntuación basada en evidencia y de los límites explícitos de evidencia no disponible.",
    ),
    (
        "A role-based staffing and sequencing plan was generated without presenting unverified market rates as committed cost.",
        "Se generó un plan de personal y secuenciación basado en roles sin presentar tarifas de mercado no verificadas como costos comprometidos.",
    ),
    (
        "Technical score, evidence limitations, roadmap, staffing, and decision boundaries were condensed into an executive briefing.",
        "La puntuación técnica, las limitaciones de evidencia, la hoja de ruta, el personal y los límites de decisión se condensaron en un resumen ejecutivo.",
    ),
    (
        "Markdown, HTML, and PDF artifacts passed identity, validity, service-name, and delivery-boundary verification.",
        "Los artefactos Markdown, HTML y PDF superaron la verificación de identidad, validez, nombre del servicio y límite de entrega.",
    ),
    (
        "A human-review request was created for the exact immutable Comprehensive report package.",
        "Se creó una solicitud de revisión humana para el paquete inmutable exacto del informe integral.",
    ),
    (
        "Automated Comprehensive work is complete. Client acceptance and delivery remain pending human approval.",
        "El trabajo integral automatizado está completo. La aceptación y la entrega al cliente siguen pendientes de aprobación humana.",
    ),
    (
        "The final native Comprehensive Markdown, HTML, JSON, and PDF draft package was generated.",
        "Se generó el paquete final nativo del borrador integral en Markdown, HTML, JSON y PDF.",
    ),
    (
        "The core decision report was generated from reconciled technical evidence.",
        "El informe principal para decisiones se generó a partir de evidencia técnica conciliada.",
    ),
    (
        "Scanner findings were separated into material, review-required, approved/nonblocking, and test-only dispositions.",
        "Los hallazgos de los analizadores se separaron en disposiciones materiales, que requieren revisión, aprobadas o no bloqueantes y exclusivas de pruebas.",
    ),
    (
        "Canonical evidence-bound technical scoring completed without forced score inflation.",
        "La puntuación técnica canónica basada en evidencia se completó sin inflar la puntuación de forma forzada.",
    ),
    ("TLS verification disabled", "Verificación TLS deshabilitada"),
    (
        "Bandit B501 retained at the exact source location.",
        "Se conservó Bandit B501 en la ubicación exacta del código fuente.",
    ),
    (
        "A network attacker could intercept trusted traffic.",
        "Un atacante en la red podría interceptar tráfico de confianza.",
    ),
    (
        "Verify that the retained source contains an executable insecure TLS call. If confirmed, restore certificate and hostname verification, remove insecure transport exceptions, add a negative regression test, and rerun exact-SHA security analysis.",
        "Verificar que el código fuente conservado contenga una llamada TLS insegura ejecutable. Si se confirma, restaurar la verificación del certificado y del nombre de host, eliminar las excepciones de transporte inseguro, agregar una prueba de regresión negativa y repetir el análisis de seguridad sobre el SHA exacto.",
    ),
    (
        "Run Bandit against the same immutable revision.",
        "Ejecutar Bandit contra la misma revisión inmutable.",
    ),
    (
        "B501 is absent from the exact-SHA scanner output.",
        "B501 no aparece en los resultados del analizador sobre el SHA exacto.",
    ),
    (
        "CI/CD Operational Readiness and Historical Health",
        "Preparación operativa y salud histórica de CI/CD",
    ),
    (
        "Operational workflow and deployment evidence is disclosed separately from exact-commit workflow-configuration maturity.",
        "La evidencia operativa de flujos de trabajo y despliegues se presenta por separado de la madurez de la configuración de flujos de trabajo del commit exacto.",
    ),
    (
        "CI/CD configuration maturity remains the immutable scored control.",
        "La madurez de la configuración de CI/CD sigue siendo el control inmutable puntuado.",
    ),
    (
        "Workflow runs, workflow jobs, and deployments are separate operational populations and have no technical-score effect.",
        "Las ejecuciones de flujos de trabajo, los trabajos y los despliegues son poblaciones operativas separadas y no afectan la puntuación técnica.",
    ),
    (
        "scanner execution evidence incomplete",
        "evidencia de ejecución del analizador incompleta",
    ),
    ("raw finding payload embedded=no", "carga de hallazgos sin procesar incluida=no"),
    ("Close material evidence and security gaps.", "Cerrar las brechas materiales de evidencia y seguridad."),
    ("Strengthen architecture and regression protection.", "Fortalecer la arquitectura y la protección contra regresiones."),
    ("Complete stakeholder-approved delivery improvements.", "Completar las mejoras de entrega aprobadas por las partes interesadas."),
    ("source: exact immutable assessment fixture", "fuente: fixture exacto de evaluación inmutable"),
    ("Unavailable or limited evidence", "Evidencia no disponible o limitada"),
    ("Evidence-Adjusted", "Ajuste por evidencia"),
    (
        "A six-month roadmap framework was derived from canonical technical findings. Dates, owners, sequencing, staffing, cost, business priority, and delivery commitments remain pending authorized stakeholder validation.",
        "Se derivó un marco de hoja de ruta de seis meses a partir de los hallazgos técnicos canónicos. Las fechas, responsables, secuencia, personal, costo, prioridad comercial y compromisos de entrega siguen pendientes de validación autorizada de las partes interesadas.",
    ),
    (
        "Role sequencing is advisory. Named people, capacity, rates, contract structure, geographic mix, budget, and commercial commitments remain pending authorized stakeholder validation.",
        "La secuencia de roles es orientativa. Las personas, capacidad, tarifas, estructura contractual, distribución geográfica, presupuesto y compromisos comerciales siguen pendientes de validación autorizada de las partes interesadas.",
    ),
    ("No canonical section scorecard was available.", "No estaba disponible el cuadro de puntuación canónico por sección."),
    ("Canonical scorecard unavailable; see the evidence limitations below.", "El cuadro de puntuación canónico no está disponible; consulte las limitaciones de evidencia."),
    ("No section summary was retained.", "No se conservó un resumen de la sección."),
    ("No structured item was retained.", "No se conservó ningún elemento estructurado."),
    ("No structured evidence line was retained for this stage.", "No se conservó ninguna línea de evidencia estructurada para esta etapa."),
    ("No assessment-wide limitation was recorded beyond stage-level disclosures.", "No se registró ninguna limitación general adicional a las declaraciones por etapa."),
    ("No retained material constraint was available beyond the human-review boundary.", "No se conservó ninguna restricción material adicional al límite de revisión humana."),
    ("Regression risk is concentrated.", "El riesgo de regresión está concentrado."),
    ("Split the module into bounded components.", "Dividir el módulo en componentes acotados."),
    ("Architecture evidence is decision ready.", "La evidencia de arquitectura está lista para apoyar decisiones."),
    ("Module boundaries and complexity were measured.", "Se midieron los límites de los módulos y la complejidad."),
    (
        "The canonical finding was retained against the assessed immutable commit.",
        "El hallazgo canónico se conservó contra el commit inmutable evaluado.",
    ),
    (
        "Human context or additional evidence is required before this section can be accepted.",
        "Se requiere contexto humano o evidencia adicional antes de aceptar esta sección.",
    ),
    (
        "Named people, rates, contract structure, geographic mix, and budget require client input.",
        "Las personas, tarifas, estructura contractual, distribución geográfica y presupuesto requieren información del cliente.",
    ),
    (
        "The exact-SHA rerun no longer reports this condition at",
        "La nueva ejecución sobre el SHA exacto ya no informa esta condición en",
    ),
    (
        "Targeted tests and the repository's full required-check suite pass on the remediation commit.",
        "Las pruebas dirigidas y el conjunto completo de verificaciones requeridas del repositorio pasan en el commit de remediación.",
    ),
    (
        "Requires human technical disposition before the condition can be treated as resolved.",
        "Requiere una disposición técnica humana antes de que la condición pueda considerarse resuelta.",
    ),
    (
        "Operations route complexity is reduced",
        "Se reduce la complejidad de la ruta de operaciones",
    ),
    (
        "No lockfile evidence was found in the captured snapshot.",
        "No se encontró evidencia de un archivo de bloqueo en la instantánea capturada.",
    ),
    (
        "One or more dependency analyzers were unavailable.",
        "Uno o más analizadores de dependencias no estaban disponibles.",
    ),
    (
        "Exact-commit sampled code signals and repository structure were reviewed.",
        "Se revisaron las señales de código muestreadas y la estructura del repositorio correspondientes al commit exacto.",
    ),
    (
        "Workflow configuration did not prove explicit permissions blocks.",
        "La configuración de los flujos de trabajo no demostró bloques explícitos de permisos.",
    ),
    (
        "Runtime user-journey execution and stakeholder acceptance testing were not available from repository evidence alone.",
        "La ejecución en tiempo real de recorridos de usuario y las pruebas de aceptación de las partes interesadas no estaban disponibles únicamente a partir de la evidencia del repositorio.",
    ),
    (
        "Dates, owners, dependencies, and budget require explicit stakeholder confirmation.",
        "Las fechas, los responsables, las dependencias y el presupuesto requieren confirmación explícita de las partes interesadas.",
    ),
    (
        "Extract state transitions, data loading, and side-effect orchestration from",
        "Extraer las transiciones de estado, la carga de datos y la orquestación de efectos secundarios de",
    ),
    (
        "into typed hooks or services; split independent rendering branches into bounded child components; add characterization and Playwright coverage; then enforce cyclomatic complexity at or below 30 for the durable source anchor.",
        "hacia hooks o servicios tipados; separar las ramas de renderizado independientes en componentes hijos acotados; agregar pruebas de caracterización y cobertura de Playwright; después exigir una complejidad ciclomática de 30 o menos para el anclaje de código fuente duradero.",
    ),
    ("into typed hooks or service", "hacia hooks o servicios tipados"),
    ("1 of 1 applicable scanner executions completed.", "Se completó 1 de 1 ejecución de analizador aplicable."),
    ("No scanner execution remains incomplete.", "No queda ninguna ejecución de analizador incompleta."),
    ("0 resulting candidates remain pending human disposition.", "0 candidatos resultantes siguen pendientes de disposición humana."),
    ("Scanner completion does not equal candidate approval.", "La finalización del analizador no equivale a la aprobación de candidatos."),
    ("Raw candidate count", "Conteo bruto de candidatos"),
    ("Confirmed material finding count", "Conteo de hallazgos materiales confirmados"),
    ("Review-required candidate count", "Conteo de candidatos que requieren revisión"),
    ("Excluded test-only count", "Conteo excluido de solo pruebas"),
    ("Approved or nonblocking count", "Conteo aprobado o no bloqueante"),
    ("confirmed material finding count=", "conteo de hallazgos materiales confirmados="),
    ("raw finding payload embedded=yes", "carga de hallazgos sin procesar incluida=sí"),
    ("Window", "Ventana"),
    ("Objective", "Objetivo"),
    ("Work Packages", "Paquetes de trabajo"),
    ("Work Package Id", "ID del paquete de trabajo"),
    ("Title", "Título"),
    ("Owner Role", "Rol responsable"),
    ("Effort", "Esfuerzo"),
    ("0-30 days", "0-30 días"),
    ("Remove the highest-risk delivery constraints.", "Eliminar las restricciones de entrega de mayor riesgo."),
    ("Decompose page.tsx", "Descomponer page.tsx"),
    ("Product Engineering Architect", "Arquitecto de ingeniería de producto"),
    ("Senior Product Engineer", "Ingeniero sénior de producto"),
    ("Product Quality Engineer", "Ingeniero de calidad de producto"),
    ("Product Engineer", "Ingeniero de producto"),
    ("Field", "Campo"),
    ("Value", "Valor"),
    ("Exact commit", "Commit exacto"),
    ("Technical maturity", "Madurez técnica"),
    ("Reviewer workload metric", "Métrica de carga del revisor"),
    ("Stable carry-forward", "Arrastre estable"),
    ("Fresh technical triage", "Nuevo triaje técnico"),
    ("triage automatizado", "triaje automatizado"),
    ("triage técnico", "triaje técnico"),
    ("Candidates requiring individual attention", "Candidatos que requieren atención individual"),
    ("Candidates covered by grouped review", "Candidatos cubiertos por revisión agrupada"),
    ("Grouped human-review clusters", "Grupos para revisión humana conjunta"),
    ("Human review work units", "Unidades de trabajo de revisión humana"),
    ("Quality-control sample pool", "Conjunto de muestra para control de calidad"),
    ("Client package boundary", "Límite del paquete del cliente"),
    (
        "Full candidate evidence, deterministic cluster membership, scanner hashes, and export-ready remediation data remain in canonical JSON and CSV.",
        "La evidencia completa de candidatos, la pertenencia determinista a grupos, los hashes de analizadores y los datos de remediación listos para exportar permanecen en JSON y CSV canónicos.",
    ),
    (
        "Full candidate evidence, deterministic cluster membership, scanner hashes, and export-ready remediation data remain in canonical JSON and",
        "La evidencia completa de candidatos, la pertenencia determinista a grupos, los hashes de analizadores y los datos de remediación listos para exportar permanecen en JSON y",
    ),
    ("Group summaries never replace underlying candidate IDs or evidence.", "Los resúmenes de grupo nunca sustituyen los ID ni la evidencia de los candidatos subyacentes."),
    ("Exact-source findings in index", "Hallazgos con fuente exacta en el índice"),
    ("Incomplete applicable analyzers", "Analizadores aplicables incompletos"),
    ("`the identified unit`", "`la unidad identificada`"),
    ("location not retained", "ubicación no conservada"),
    ("requires review", "requiere revisión"),
    ("observed", "observado"),
    ("Impact", "Impacto"),
    ("Recommendation", "Recomendación"),
    ("owner=", "responsable="),
    ("effort=", "esfuerzo="),
    ("Assessment-wide", "Evaluación general"),
    ("unavailable", "no disponible"),
    ("FRAMEWORK_ONLY", "SOLO_MARCO"),
    ("REVIEW_REQUIRED", "REQUIERE_REVISIÓN"),
    ("TIMED_OUT", "TIEMPO_AGOTADO"),
    ("NOT SCORED", "SIN PUNTUACIÓN"),
    ("VERIFIED", "VERIFICADO"),
    ("COMPLETE", "COMPLETO"),
    ("PENDING", "PENDIENTE"),
    ("Pending", "Pendiente"),
    ("MODERATE", "MODERADO"),
    ("STRONG", "SÓLIDO"),
    ("BLOCKED", "BLOQUEADO"),
    ("FAILED", "FALLIDO"),
    ("GREEN", "VERDE"),
    ("YELLOW", "AMARILLO"),
    ("RED", "ROJO"),
    ("GRAY", "GRIS"),
    ("UNAVAILABLE", "NO DISPONIBLE"),
    ("RUNNING", "EN EJECUCIÓN"),
    ("QUEUED", "EN COLA"),
    ("UNKNOWN", "DESCONOCIDO"),
)
_PRESENTATION_REPLACEMENTS += tuple(_ES_PHRASES.items())

# The active native providers build the canonical English report truth before
# locale selection. These are their renderer-visible templates. Keep them here
# as exact source/target pairs so the Spanish renderer preserves every claim,
# qualifier, and evidence boundary without changing the English providers.
_PRESENTATION_REPLACEMENTS += (
    (
        "Proceed to human review; do not authorize client delivery until evidence limitations and recommendations are approved.",
        "Proceder a la revisión humana; no autorizar la entrega al cliente hasta que se aprueben las limitaciones de evidencia y las recomendaciones.",
    ),
    (
        "Proceed to human review; client delivery remains blocked.",
        "Proceder a la revisión humana; la entrega al cliente permanece bloqueada.",
    ),
    (
        "Client delivery remains blocked until explicit authorized human approval",
        "La entrega al cliente permanece bloqueada hasta que exista una aprobación humana autorizada y explícita",
    ),
    (
        "NICO automated technical triage completed; authorized human disposition remains pending.",
        "El triaje técnico automatizado de NICO se completó; la disposición humana autorizada sigue pendiente.",
    ),
    (
        "Score effect: assurance-only while authorized human disposition remains pending; NICO technical-triage status is reported separately.",
        "Efecto en la puntuación: solo aseguramiento mientras la disposición humana autorizada siga pendiente; el estado del triaje técnico de NICO se informa por separado.",
    ),
    (
        "Architecture and evidence governance.",
        "Arquitectura y gobernanza de la evidencia.",
    ),
    (
        "Scanner candidates remain separate from confirmed material findings. NICO completed deterministic technical triage, retained valid same-subject prior analysis, grouped homogeneous repetitive review work, and routed genuine exceptions without creating human disposition or approval.",
        "Los candidatos de analizadores permanecen separados de los hallazgos materiales confirmados. NICO completó un triaje técnico determinista, conservó análisis previos válidos del mismo sujeto de evaluación, agrupó trabajo de revisión repetitivo y homogéneo y encaminó las excepciones genuinas sin crear disposición ni aprobación humana.",
    ),
    (
        "Technical triage remains proposal-only. Authorized human approval remains pending and client delivery remains blocked.",
        "El triaje técnico sigue siendo únicamente una propuesta. La aprobación humana autorizada sigue pendiente y la entrega al cliente permanece bloqueada.",
    ),
    (
        "CI/CD operational readiness and historical workflow outcomes are reported separately and have no technical-score effect.",
        "La preparación operativa de CI/CD y los resultados históricos de los flujos de trabajo se informan por separado y no afectan la puntuación técnica.",
    ),
    (
        "B. Current operational readiness: not established by repository evidence alone; exact deployed frontend/backend commit proof and current production acceptance must be attached.",
        "B. Preparación operativa actual: no se establece únicamente con evidencia del repositorio; deben adjuntarse la prueba del commit exacto desplegado en frontend/backend y la aceptación actual de producción.",
    ),
    (
        "C. Required-check health: not treated as passed unless exact required-check records for the assessed or release commit are attached.",
        "C. Estado de las verificaciones requeridas: no se considera aprobado a menos que se adjunten los registros exactos de las verificaciones requeridas para el commit evaluado o de publicación.",
    ),
    ("authorized defensive repository assessment", "evaluación defensiva autorizada del repositorio"),
    (
        "No successful workflow run was available in the bounded history window.",
        "No hubo ninguna ejecución satisfactoria de un flujo de trabajo en la ventana histórica acotada.",
    ),
    (
        "Complexity evidence reports concentrated high-risk hotspots.",
        "La evidencia de complejidad muestra puntos críticos concentrados de alto riesgo.",
    ),
    (
        "Commit or pull-request history was incomplete for delivery-process analysis.",
        "El historial de commits o solicitudes de incorporación estaba incompleto para analizar el proceso de entrega.",
    ),
    (
        "Manifest, lockfile, and scanner evidence were reconciled.",
        "Se concilió la evidencia de manifiestos, archivos de bloqueo y analizadores.",
    ),
    (
        "Secret-scanner candidates are separated from verified material findings.",
        "Los candidatos de los analizadores de secretos se separan de los hallazgos materiales verificados.",
    ),
    (
        "Static analyzers were executed against the immutable snapshot and reconciled by disposition.",
        "Los analizadores estáticos se ejecutaron contra la instantánea inmutable y se conciliaron por disposición.",
    ),
    (
        "Workflow configuration and bounded operational history were reviewed separately.",
        "La configuración de los flujos de trabajo y el historial operativo acotado se revisaron por separado.",
    ),
    (
        "Snapshot-bound source footprint and measured complexity evidence were evaluated.",
        "Se evaluaron la huella del código fuente vinculada a la instantánea y la evidencia de complejidad medida.",
    ),
    (
        "Commit, PR, workflow, source-footprint, and complexity evidence inform work-vs-expected review.",
        "La evidencia de commits, solicitudes de incorporación, flujos de trabajo, huella del código fuente y complejidad sustenta la revisión del trabajo frente a lo esperado.",
    ),
    ("Core technical evidence for", "La evidencia técnica principal de"),
    ("produced an evidence-bound", "produjo una señal de madurez basada en evidencia de nivel"),
    (
        "/100). Comprehensive-only modules continue after this score and remain subject to human review.",
        "/100). Los módulos exclusivos de la evaluación integral continúan después de esta puntuación y siguen sujetos a revisión humana.",
    ),
    ("Automated evidence coverage", "Cobertura automatizada de evidencia"),
    (
        "No native iOS or Android project evidence was observed in the bounded repository sample; cross-platform parity cannot be scored.",
        "No se observó evidencia de proyectos nativos de iOS o Android en la muestra acotada del repositorio; no puede puntuarse la paridad entre plataformas.",
    ),
    (
        "No authoritative requirements register or stakeholder-approved acceptance matrix was present in the bounded repository sample.",
        "No había un registro autoritativo de requisitos ni una matriz de aceptación aprobada por las partes interesadas en la muestra acotada del repositorio.",
    ),
    (
        "Stabilize material security, dependency, CI, and evidence-integrity findings.",
        "Estabilizar los hallazgos materiales de seguridad, dependencias, CI e integridad de la evidencia.",
    ),
    (
        "Strengthen tests, architecture boundaries, deployment controls, and operational observability.",
        "Reforzar las pruebas, los límites de arquitectura, los controles de despliegue y la observabilidad operativa.",
    ),
    (
        "Execute platform, stakeholder, requirements, and delivery-maturity improvements with measurable acceptance criteria.",
        "Ejecutar mejoras de plataforma, partes interesadas, requisitos y madurez de entrega con criterios de aceptación medibles.",
    ),
    (
        "Architecture, scoring validation, risk disposition, and roadmap governance.",
        "Arquitectura, validación de puntuación, disposición de riesgos y gobernanza de la hoja de ruta.",
    ),
    (
        "Dependency, CI/CD, backend, frontend, and deployment remediation.",
        "Remediación de dependencias, CI/CD, backend, frontend y despliegue.",
    ),
    (
        "Functional QA, platform parity, report truth, and release acceptance.",
        "QA funcional, paridad de plataformas, veracidad del informe y aceptación de la publicación.",
    ),
    (
        "Stakeholder interviews, business priorities, budget authority, and acceptance criteria were not supplied in the repository evidence package.",
        "El paquete de evidencia del repositorio no incluyó entrevistas con las partes interesadas, prioridades comerciales, autoridad presupuestaria ni criterios de aceptación.",
    ),
    (
        "Change-failure rate and recovery time remain estimates unless incidents and production telemetry are supplied.",
        "La tasa de fallos de cambios y el tiempo de recuperación siguen siendo estimaciones mientras no se aporten incidentes y telemetría de producción.",
    ),
    (
        "Dates, owners, and budget require stakeholder approval before becoming commitments.",
        "Las fechas, los responsables y el presupuesto requieren la aprobación de las partes interesadas antes de convertirse en compromisos.",
    ),
    (
        "Labor rates, contract structure, geographic mix, and budget ceilings require client input before cost finalization.",
        "Las tarifas laborales, la estructura contractual, la distribución geográfica y los límites presupuestarios requieren aportes del cliente antes de finalizar los costos.",
    ),
    ("Raw scanner candidates:", "Candidatos sin procesar de los analizadores:"),
    ("Risk pattern hits:", "Coincidencias de patrones de riesgo:"),
    ("Test paths in tree:", "Rutas de prueba en el árbol:"),
    ("Dependency entries:", "Entradas de dependencias:"),
    ("Lockfiles:", "Archivos de bloqueo:"),
    ("Material findings:", "Hallazgos materiales:"),
    ("Review-required candidates:", "Candidatos que requieren revisión:"),
    ("Tools run:", "Herramientas ejecutadas:"),
    ("Failed tools:", "Herramientas fallidas:"),
    ("Timed-out tools:", "Herramientas con tiempo agotado:"),
    ("Workflow files:", "Archivos de flujos de trabajo:"),
    ("Successful runs:", "Ejecuciones exitosas:"),
    ("Non-success runs:", "Ejecuciones no exitosas:"),
    ("Source files:", "Archivos de código fuente:"),
    ("Complexity risk:", "Riesgo de complejidad:"),
    ("Commits returned:", "Commits obtenidos:"),
    ("Pull requests returned:", "Solicitudes de incorporación obtenidas:"),
    ("Files analyzed for complexity:", "Archivos analizados por complejidad:"),
    ("Unavailable tools:", "Herramientas no disponibles:"),
    ("Verified material:", "Material verificado:"),
    ("Applicable analyzers:", "Analizadores aplicables:"),
    ("Raw candidates:", "Candidatos brutos:"),
    ("Review required:", "Revisión requerida:"),
    ("Approved/nonblocking:", "Aprobados/no bloqueantes:"),
    ("Excluded non-production/test-only:", "Excluidos por no ser de producción o ser solo de pruebas:"),
    ("Historical non-success runs:", "Ejecuciones históricas no exitosas:"),
    ("Configuration controls:", "Controles de configuración:"),
    ("Runs matching assessed SHA:", "Ejecuciones que coinciden con el SHA evaluado:"),
    ("Merged pull requests:", "Solicitudes de incorporación fusionadas:"),
    ("Observed job success rate:", "Tasa de éxito observada de trabajos:"),
    ("Executable code-risk findings:", "Hallazgos de riesgo en código ejecutable:"),
    ("Excluded non-production observations:", "Observaciones excluidas por no ser de producción:"),
    ("Example placeholder secrets retained separately:", "Secretos de ejemplo conservados por separado:"),
    ("Source analysis:", "Análisis de código fuente:"),
    ("Applicable exact-SHA analyzer coverage", "Cobertura de analizadores aplicables del SHA exacto"),
    ("Exact-SHA analyzer execution coverage", "Cobertura de ejecución de analizadores del SHA exacto"),
    ("31-90 days", "31-90 días"),
    ("91-180 days", "91-180 días"),
    (
        "No workflow configuration was retained at the assessed commit.",
        "No se conservó ninguna configuración de flujos de trabajo en el commit evaluado.",
    ),
    (
        "Explicit workflow permission boundaries were not proven.",
        "No se demostraron límites explícitos de permisos en los flujos de trabajo.",
    ),
    (
        "No successful workflow run was retained in the bounded history window.",
        "No se conservó ninguna ejecución satisfactoria de un flujo de trabajo en la ventana histórica acotada.",
    ),
    (
        "Authoritative manifests and contextual dependency-analyzer evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.",
        "Los manifiestos autoritativos y la evidencia contextual de los analizadores de dependencias se conciliaron por paquete, versión instalada, aviso, versión corregida, ruta, alcance y accesibilidad.",
    ),
    (
        "No lockfile evidence was retained in the captured snapshot.",
        "No se conservó evidencia de archivos de bloqueo en la instantánea capturada.",
    ),
    (
        "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.",
        "La evidencia de secretos con conocimiento del historial se separó en hallazgos materiales verificados, candidatos que requieren revisión, marcadores explícitos de ejemplo y observaciones ajenas a producción.",
    ),
    (
        "Bandit, Semgrep, ESLint, and TypeScript evidence were evaluated independently against the exact immutable commit.",
        "La evidencia de Bandit, Semgrep, ESLint y TypeScript se evaluó de forma independiente contra el commit inmutable exacto.",
    ),
    (
        "Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.",
        "Se analizaron las señales ejecutables del código fuente del commit exacto sin convertir comentarios, cadenas, definiciones de detectores, ejemplos ni pruebas en defectos.",
    ),
    (
        "Current job, deployment, exact-SHA, workflow-control, and separately labeled historical evidence were evaluated.",
        "Se evaluó la evidencia actual de trabajos, despliegues, SHA exacto y controles de flujos de trabajo, junto con la evidencia histórica etiquetada por separado.",
    ),
    (
        "Snapshot-bound source footprint and measured complexity evidence were evaluated without score override.",
        "Se evaluaron la huella del código fuente vinculada a la instantánea y la evidencia de complejidad medida sin sobrescribir la puntuación.",
    ),
    (
        "Commit, pull-request, merge, and current job evidence inform delivery throughput without evaluating individual developer performance.",
        "La evidencia de commits, solicitudes de incorporación, fusiones y trabajos actuales sustenta el rendimiento de entrega sin evaluar el desempeño individual de los desarrolladores.",
    ),
    ("Exact-SHA technical evidence for", "La evidencia técnica del SHA exacto de"),
    (
        "/100) and independently evidence-adjusted score of",
        "/100) y una puntuación independiente ajustada por evidencia de",
    ),
    (
        "/100. No score was raised without retained evidence.",
        "/100. No se elevó ninguna puntuación sin evidencia conservada.",
    ),
    (
        "Canonical technical and evidence-adjusted scoring completed from category-specific retained evidence without commercial score targeting.",
        "La puntuación técnica canónica y la ajustada por evidencia se completaron a partir de evidencia conservada específica de cada categoría, sin perseguir una puntuación comercial.",
    ),
    (
        "Commit history was unavailable for delivery-process analysis.",
        "El historial de commits no estaba disponible para analizar el proceso de entrega.",
    ),
    (
        "Pull-request history was unavailable for delivery-process analysis.",
        "El historial de solicitudes de incorporación no estaba disponible para analizar el proceso de entrega.",
    ),
    (
        "Current bounded job success evidence is below 90%.",
        "La evidencia acotada actual de trabajos satisfactorios está por debajo del 90 %.",
    ),
    (
        "Group only explicit dependency or secret review candidates.",
        "Agrupar únicamente candidatos explícitos para revisión de dependencias o secretos.",
    ),
    (
        "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.",
        "Los resultados históricos de flujos de trabajo, trabajos y despliegues se conservan como una tendencia operativa sin puntuación.",
    ),
    (
        "The delivery-capacity score is 60% architecture maintainability and 40% immutable workflow automation.",
        "La puntuación de capacidad de entrega se compone de un 60 % de mantenibilidad de la arquitectura y un 40 % de automatización inmutable de los flujos de trabajo.",
    ),
    (
        "Commit, pull-request, merge, job, and deployment counts are retained as trend context and have no score effect.",
        "Los conteos de commits, solicitudes de incorporación, fusiones, trabajos y despliegues se conservan como contexto de tendencia y no afectan la puntuación.",
    ),
    (
        "CI/CD technical maturity is scored only from workflow configuration bound to the exact immutable commit; later operational outcomes are reported separately.",
        "La madurez técnica de CI/CD se puntúa únicamente a partir de la configuración de flujos de trabajo vinculada al commit inmutable exacto; los resultados operativos posteriores se informan por separado.",
    ),
    (
        "Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.",
        "La capacidad de entrega sostenible se deriva de la mantenibilidad inmutable de la arquitectura y la automatización de los flujos de trabajo; el volumen de actividad mutable es contexto sin puntuación.",
    ),
    (
        "No workflow configuration was retained at the assessed commit.",
        "No se conservó ninguna configuración de flujos de trabajo en el commit evaluado.",
    ),
    (
        "Workflow configuration was not proven against the exact assessed commit.",
        "La configuración de los flujos de trabajo no se demostró contra el commit exacto evaluado.",
    ),
    (
        "Explicit workflow permission boundaries were not proven at the assessed commit.",
        "No se demostraron límites explícitos de permisos de los flujos de trabajo en el commit evaluado.",
    ),
    ("Workflow files at assessed commit:", "Archivos de flujos de trabajo en el commit evaluado:"),
    ("Workflow configuration exact-SHA match:", "Coincidencia de SHA exacto de la configuración de flujos de trabajo:"),
    ("Explicit permissions present:", "Permisos explícitos presentes:"),
    ("Immutable workflow controls present:", "Controles inmutables de flujos de trabajo presentes:"),
    ("Architecture and technical-debt score:", "Puntuación de arquitectura y deuda técnica:"),
    ("Immutable CI configuration score:", "Puntuación de la configuración inmutable de CI:"),
    (
        "Concentrated architecture or complexity risk constrains sustainable delivery capacity.",
        "El riesgo concentrado de arquitectura o complejidad limita la capacidad de entrega sostenible.",
    ),
    (
        "Canonical scoring completed from immutable code, workflow configuration, and exact-SHA scanner evidence; mutable operational trends were retained without affecting technical scores.",
        "La puntuación canónica se completó a partir de código inmutable, configuración de flujos de trabajo y evidencia de analizadores con SHA exacto; las tendencias operativas mutables se conservaron sin afectar las puntuaciones técnicas.",
    ),
    (
        "Technical-score impact is limited to verified material findings and incomplete applicable analyzer execution.",
        "El impacto en la puntuación técnica se limita a hallazgos materiales verificados y ejecuciones incompletas de analizadores aplicables.",
    ),
    (
        "/100) and evidence-adjusted readiness of",
        "/100) y una preparación ajustada por evidencia de",
    ),
    (
        "/100. Only verified material findings and incomplete applicable analyzers affect technical scores; unverified candidate volume affects assurance only.",
        "/100. Solo los hallazgos materiales verificados y los analizadores aplicables incompletos afectan las puntuaciones técnicas; el volumen de candidatos no verificados afecta únicamente el aseguramiento.",
    ),
    (
        "Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.",
        "Los manifiestos autoritativos y la evidencia contextual de dependencias se conciliaron por paquete, versión instalada, aviso, versión corregida, ruta, alcance y accesibilidad.",
    ),
    (
        "Canonical scoring completed from immutable technical evidence with verified-material technical scoring, assurance-only review candidates, completed-with-findings execution truth, and synchronized score aliases.",
        "La puntuación canónica se completó a partir de evidencia técnica inmutable, con puntuación técnica de material verificado, candidatos de revisión que solo afectan el aseguramiento, verdad de ejecución completada con hallazgos y alias de puntuación sincronizados.",
    ),
    (
        "Canonical scoring completed from exact-SHA technical evidence and a count-reconciled scanner finding register. Unresolved candidate volume now changes evidence-adjusted readiness without being misrepresented as confirmed defect severity.",
        "La puntuación canónica se completó a partir de evidencia técnica con SHA exacto y un registro de hallazgos de analizadores conciliado por conteo. El volumen de candidatos sin resolver modifica la preparación ajustada por evidencia sin presentarse incorrectamente como gravedad de defectos confirmados.",
    ),
    (
        "Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or Evidence-Adjusted score effect.",
        "El volumen de candidatos y la carga de trabajo de revisión son métricas operativas de revisión y no tienen efecto numérico en la madurez técnica ni en la puntuación ajustada por evidencia.",
    ),
    (
        "This analyzer candidate requires validation before it can be treated as a confirmed technical defect.",
        "Este candidato de analizador requiere validación antes de poder tratarse como un defecto técnico confirmado.",
    ),
    (
        "Validate the rule against the exact file and revision, group equivalent instances, then remediate or approve a bounded exception.",
        "Validar la regla contra el archivo y la revisión exactos, agrupar las instancias equivalentes y después remediar o aprobar una excepción acotada.",
    ),
    (
        "The originating analyzer completes on the exact SHA and the grouped candidate is resolved or approved with traceable rationale.",
        "El analizador de origen se completa en el SHA exacto y el candidato agrupado se resuelve o aprueba con una justificación trazable.",
    ),
    (
        "Static Analysis is not scored because required current-run analyzer evidence is incomplete. Candidate findings remain visible for human disposition without being treated as proven critical code quality.",
        "El análisis estático no recibe puntuación porque la evidencia requerida de los analizadores de la ejecución actual está incompleta. Los hallazgos candidatos siguen visibles para la disposición humana sin tratarse como problemas críticos demostrados de calidad del código.",
    ),
    (
        "Concentrated frontend complexity",
        "Complejidad concentrada en el frontend",
    ),
    (
        "Large, highly branched modules increase regression risk, review cost, and the difficulty of safe change.",
        "Los módulos grandes y con muchas ramificaciones aumentan el riesgo de regresión, el costo de revisión y la dificultad de realizar cambios seguros.",
    ),
    (
        "Static-analysis evidence incomplete",
        "Evidencia de análisis estático incompleta",
    ),
    (
        "Incomplete analyzer execution prevents a defensible technical conclusion for the affected control.",
        "La ejecución incompleta de analizadores impide una conclusión técnica defendible para el control afectado.",
    ),
    (
        "Repair the failed analyzer boundary and retain two consecutive exact-SHA successful runs before assigning a technical score.",
        "Reparar el límite del analizador fallido y conservar dos ejecuciones exitosas consecutivas para el SHA exacto antes de asignar una puntuación técnica.",
    ),
    (
        "Unverified medium-severity candidates may represent real hardening opportunities, but they are not yet confirmed defects.",
        "Los candidatos no verificados de gravedad media pueden representar oportunidades reales de refuerzo, pero todavía no son defectos confirmados.",
    ),
    (
        "Group equivalent rules, validate representative instances, and remediate confirmed issues by theme rather than repeating identical work items.",
        "Agrupar las reglas equivalentes, validar instancias representativas y remediar los problemas confirmados por tema, en lugar de repetir elementos de trabajo idénticos.",
    ),
    (
        "Dependency findings require disposition",
        "Los hallazgos de dependencias requieren disposición",
    ),
    (
        "Confirmed vulnerable or unsupported dependencies can create security, stability, and maintenance exposure.",
        "Las dependencias vulnerables o sin soporte confirmadas pueden generar exposición de seguridad, estabilidad y mantenimiento.",
    ),
    (
        "Triage the retained dependency findings, upgrade or constrain affected packages, regenerate lockfiles, and rerun all dependency analyzers.",
        "Clasificar los hallazgos de dependencias conservados, actualizar o restringir los paquetes afectados, regenerar los archivos de bloqueo y volver a ejecutar todos los analizadores de dependencias.",
    ),
    (
        "Secret-history assurance remains review-limited",
        "El aseguramiento del historial de secretos sigue limitado por revisión",
    ),
    (
        "Incomplete or unverified history coverage prevents a clean credential-exposure conclusion.",
        "La cobertura incompleta o no verificada del historial impide una conclusión limpia sobre la exposición de credenciales.",
    ),
    (
        "Complete history scanning, validate retained candidates without exposing raw values, and rotate any confirmed live credential.",
        "Completar el análisis del historial, validar los candidatos conservados sin exponer valores sin procesar y rotar cualquier credencial activa confirmada.",
    ),
    (
        "Historical CI failures need cause classification",
        "Los fallos históricos de CI necesitan clasificación de causas",
    ),
    (
        "Unclassified non-success runs obscure release reliability and can conceal recurring operational defects.",
        "Las ejecuciones no exitosas sin clasificar dificultan evaluar la fiabilidad de las publicaciones y pueden ocultar defectos operativos recurrentes.",
    ),
    (
        "Separate cancellations from failures, classify recurring causes, assign owners, and publish a rolling reliability trend.",
        "Separar las cancelaciones de los fallos, clasificar las causas recurrentes, asignar responsables y publicar una tendencia móvil de fiabilidad.",
    ),
    (
        "Bounded code-risk patterns require exact-location review",
        "Los patrones acotados de riesgo de código requieren revisión de la ubicación exacta",
    ),
    (
        "Pattern matches may indicate unsafe APIs or may be benign framework behavior; confirmation is required before escalation.",
        "Las coincidencias de patrones pueden indicar API inseguras o comportamientos benignos del framework; se requiere confirmación antes de escalar.",
    ),
    (
        "Review the retained locations as one remediation theme, disposition each match, and rerun against the same immutable revision.",
        "Revisar las ubicaciones conservadas como un solo tema de remediación, decidir la disposición de cada coincidencia y volver a ejecutar contra la misma revisión inmutable.",
    ),
    (
        "Static-analysis assurance remains review-limited",
        "El aseguramiento del análisis estático sigue limitado por revisión",
    ),
    (
        "Accepted Semgrep, TypeScript, and bounded triage evidence supports a conservative technical signal, but incomplete live analyzer acceptance prevents verified assurance.",
        "La evidencia aceptada de Semgrep, TypeScript y triaje acotado respalda una señal técnica conservadora, pero la aceptación incompleta de analizadores en ejecución impide un aseguramiento verificado.",
    ),
    (
        "Repair the failed analyzer boundary, complete rule-level candidate triage, and retain two consecutive exact-SHA successful runs before promoting the control to verified assurance.",
        "Reparar el límite del analizador fallido, completar el triaje de candidatos a nivel de regla y conservar dos ejecuciones exitosas consecutivas para el SHA exacto antes de promover el control a aseguramiento verificado.",
    ),
    (
        "Cancellations are excluded from the genuine-failure rate.",
        "Las cancelaciones se excluyen de la tasa de fallos reales.",
    ),
    (
        "Bounded historical reliability is reported separately and does not change assessed-commit health.",
        "La fiabilidad histórica acotada se informa por separado y no modifica el estado del commit evaluado.",
    ),
    (
        "Unique measured regions classified by source role; only active production functions/components and report-generation functions at cyclomatic complexity >=30 are actionable.",
        "Regiones medidas únicas clasificadas por función del código fuente; solo son accionables las funciones o componentes activos de producción y las funciones de generación de informes con complejidad ciclomática >=30.",
    ),
    (
        "No exact-commit required-check record was retained; historical or default-branch state is not substituted.",
        "No se conservó ningún registro de verificaciones requeridas para el commit exacto; no se sustituye por el estado histórico ni por el de la rama predeterminada.",
    ),
    (
        "Only exact-SHA retained evidence changes report outcomes; unchanged risks remain visible.",
        "Solo la evidencia conservada para el SHA exacto modifica los resultados del informe; los riesgos sin cambios siguen visibles.",
    ),
    (
        "Assurance is constrained; no client defect is inferred.",
        "El aseguramiento está limitado; no se infiere ningún defecto del cliente.",
    ),
    (
        "Close evidence-integrity and release-reliability gaps before expanding client use.",
        "Cerrar las brechas de integridad de la evidencia y fiabilidad de las publicaciones antes de ampliar el uso por parte del cliente.",
    ),
    (
        "Eliminate worker resource failures, complete required analyzers, and retain exact finding locations without secret leakage.",
        "Eliminar los fallos de recursos de los procesos de trabajo, completar los analizadores requeridos y conservar las ubicaciones exactas de los hallazgos sin filtrar secretos.",
    ),
    (
        "Bandit, Semgrep, Gitleaks, and TruffleHog complete twice against one exact SHA",
        "Bandit, Semgrep, Gitleaks y TruffleHog se completan dos veces contra un mismo SHA exacto",
    ),
    (
        "Every candidate has category, tool, severity, and safe location",
        "Cada candidato tiene categoría, herramienta, gravedad y ubicación segura",
    ),
    (
        "Classify and reduce CI/CD non-success history",
        "Clasificar y reducir el historial de ejecuciones no exitosas de CI/CD",
    ),
    (
        "All retained non-success runs are cause-classified",
        "Todas las ejecuciones no exitosas conservadas tienen su causa clasificada",
    ),
    (
        "Recurring failure classes have owners and fixes",
        "Las clases de fallos recurrentes tienen responsables y correcciones",
    ),
    (
        "Two consecutive acceptance windows meet the approved success threshold",
        "Dos ventanas de aceptación consecutivas cumplen el umbral de éxito aprobado",
    ),
    (
        "Reduce concentrated technical debt and make requirements traceable to acceptance evidence.",
        "Reducir la deuda técnica concentrada y hacer que los requisitos sean trazables hasta la evidencia de aceptación.",
    ),
    (
        "Decompose the highest-complexity hotspots",
        "Descomponer los puntos críticos de mayor complejidad",
    ),
    (
        "Reduce concentrated complexity and duplicate logic while preserving behavior through characterization tests.",
        "Reducir la complejidad concentrada y la lógica duplicada mientras se preserva el comportamiento mediante pruebas de caracterización.",
    ),
    (
        "Top hotspots are split into bounded modules",
        "Los principales puntos críticos se dividen en módulos acotados",
    ),
    (
        "Target complexity and nesting thresholds pass",
        "Se cumplen los umbrales objetivo de complejidad y anidamiento",
    ),
    (
        "Every committed requirement has an owner and acceptance test",
        "Cada requisito comprometido tiene un responsable y una prueba de aceptación",
    ),
    (
        "Prove the complete operating model through telemetry, recovery evidence, and authorized external pilots.",
        "Demostrar el modelo operativo completo mediante telemetría, evidencia de recuperación y pilotos externos autorizados.",
    ),
    (
        "Validate user journeys, incident recovery, performance, and report usefulness on an authorized external repository.",
        "Validar los recorridos de usuario, la recuperación ante incidentes, el rendimiento y la utilidad del informe en un repositorio externo autorizado.",
    ),
    (
        "Express and Comprehensive complete on the pilot repository",
        "Express y Comprehensive se completan en el repositorio piloto",
    ),
    (
        "Backup/restore and restart recovery evidence is retained",
        "Se conserva evidencia de copia de seguridad, restauración y recuperación tras reinicio",
    ),
    (
        "Reviewer approves or rejects the immutable package",
        "La persona revisora aprueba o rechaza el paquete inmutable",
    ),
    (
        "No client-specific labor rates, revenue, incident cost, or contract-penalty inputs were supplied.",
        "No se suministraron tarifas laborales, ingresos, costos de incidentes ni penalizaciones contractuales específicas del cliente.",
    ),
    (
        "Scanner candidate retained without a human-readable message.",
        "Candidato de analizador conservado sin un mensaje legible para personas.",
    ),
    (
        "CI/CD configuration maturity is exact-SHA technical evidence. Observed workflow outcomes are reported separately as mutable operational health.",
        "La madurez de la configuración de CI/CD es evidencia técnica con SHA exacto. Los resultados observados de los flujos de trabajo se informan por separado como salud operativa mutable.",
    ),
    (
        "Every retained scanner candidate was normalized into a deterministic canonical register or explicitly represented as count-only evidence when the raw payload was unavailable.",
        "Cada candidato de analizador conservado se normalizó en un registro canónico determinista o se representó explícitamente como evidencia de solo conteo cuando la carga sin procesar no estaba disponible.",
    ),
    (
        "Scanner finding counts could not be reconciled to the canonical finding register.",
        "Los conteos de hallazgos de analizadores no pudieron conciliarse con el registro canónico de hallazgos.",
    ),
    (
        "One or more scanner categories retained candidate counts without raw payloads; those candidates remain review-required and reduce evidence-adjusted readiness.",
        "Una o más categorías de analizadores conservaron conteos de candidatos sin cargas sin procesar; esos candidatos siguen requiriendo revisión y reducen la preparación ajustada por evidencia.",
    ),
    (
        "Approved journey matrix, runtime environment, observed results, and acceptance criteria.",
        "Matriz de recorridos aprobada, entorno de ejecución, resultados observados y criterios de aceptación.",
    ),
    (
        "Supported device/platform matrix with observed runtime results and approved parity criteria.",
        "Matriz de dispositivos y plataformas compatibles con resultados de ejecución observados y criterios de paridad aprobados.",
    ),
    (
        "Authorized objectives, constraints, success measures, decision owners, and authority records.",
        "Objetivos autorizados, restricciones, medidas de éxito, responsables de decisiones y registros de autoridad.",
    ),
    (
        "Approved requirements/specifications/ADRs/acceptance criteria with owner and source reference.",
        "Requisitos, especificaciones, ADR y criterios de aceptación aprobados, con responsable y referencia de fuente.",
    ),
    (
        "Incident, deployment/rollback, and measured recovery records.",
        "Registros de incidentes, despliegues o reversiones y recuperación medida.",
    ),
    (
        "Exact-source maintainability, complexity hotspots, coupling, duplication, workflow automation, and bounded change history were synthesized; activity volume remains unscored context.",
        "Se sintetizaron la mantenibilidad con fuente exacta, los puntos críticos de complejidad, el acoplamiento, la duplicación, la automatización de flujos de trabajo y el historial acotado de cambios; el volumen de actividad sigue siendo contexto sin puntuación.",
    ),
    (
        "Hotspots, coupling, and duplication are evidence-bound to the retained exact-SHA sampled source set.",
        "Los puntos críticos, el acoplamiento y la duplicación están vinculados por evidencia al conjunto muestreado de código fuente del SHA exacto conservado.",
    ),
    (
        "Repository test inventory, supplied journey evidence, parsed results, coverage gaps, and draft QA conclusions were reconciled without treating repository tests or model synthesis as runtime acceptance.",
        "Se conciliaron el inventario de pruebas del repositorio, la evidencia aportada de recorridos, los resultados analizados, las brechas de cobertura y las conclusiones preliminares de QA sin tratar las pruebas del repositorio ni la síntesis del modelo como aceptación en ejecución.",
    ),
    (
        "Repository platform indicators and supplied feature/device observations were reconciled and divergence candidates surfaced without promoting source indicators or an unapproved matrix to runtime/device parity.",
        "Se conciliaron los indicadores de plataforma del repositorio y las observaciones aportadas de funciones y dispositivos, y se identificaron candidatos de divergencia sin convertir indicadores de código fuente ni una matriz no aprobada en paridad de ejecución o dispositivos.",
    ),
    (
        "Supplied stakeholder/business evidence was organized, linked to the engagement, and checked for conflicts while authority and disputed meaning remain human decisions.",
        "La evidencia comercial y de las partes interesadas aportada se organizó, se vinculó al encargo y se comprobó en busca de conflictos, mientras que la autoridad y los significados controvertidos siguen siendo decisiones humanas.",
    ),
    (
        "Supplied requirements were mapped to retained implementation paths where supportable, with authoritative, supplied-unverified, inferred, missing, and verification states explicit.",
        "Los requisitos aportados se vincularon, cuando era justificable, con las rutas de implementación conservadas, dejando explícitos los estados autoritativo, aportado sin verificar, inferido, faltante y de verificación.",
    ),
    (
        "Supplied observed results include one or more failed outcomes; professional review and remediation evidence are required.",
        "Los resultados observados aportados incluyen uno o más resultados fallidos; se requieren revisión profesional y evidencia de remediación.",
    ),
    (
        "Supplied observed results contain no parsed failure token, but this synthesis is not stakeholder acceptance or production certification.",
        "Los resultados observados aportados no contienen ningún indicador de fallo analizado, pero esta síntesis no constituye aceptación de las partes interesadas ni certificación de producción.",
    ),
    (
        "No observed runtime result was supplied.",
        "No se aportó ningún resultado observado en ejecución.",
    ),
    (
        "trufflehog: temporary workspace clone could not retrieve a lazy Git object",
        "trufflehog: el clon temporal del espacio de trabajo no pudo recuperar un objeto de Git con carga diferida",
    ),
    (
        "No complete retained exact-SHA scanner artifact was available.",
        "No había disponible ningún artefacto completo y conservado de analizadores para el SHA exacto.",
    ),
    (
        "Every supplied critical journey needs a retained observed result before the evidence set is complete.",
        "Cada recorrido crítico aportado necesita un resultado observado y conservado antes de que el conjunto de evidencia esté completo.",
    ),
    (
        "Complete runtime coverage for the supplied journey matrix.",
        "Cobertura completa en ejecución de la matriz de recorridos aportada.",
    ),
    (
        "Observed result records for the remaining supplied test cases.",
        "Registros de resultados observados para los casos de prueba aportados restantes.",
    ),
    (
        "Supplied requirements need an authority classification before contractual or approved conformance can be asserted.",
        "Los requisitos aportados necesitan una clasificación de autoridad antes de poder afirmar conformidad contractual o aprobada.",
    ),
    (
        "Whether the affected statements are approved obligations, drafts, or informal notes.",
        "Si las declaraciones afectadas son obligaciones aprobadas, borradores o notas informales.",
    ),
    (
        "Authority status and source provenance for each supplied requirement set.",
        "Estado de autoridad y procedencia de la fuente de cada conjunto de requisitos aportado.",
    ),
    (
        "Bounded operational history and supplied incident evidence were reconciled without turning activity volume into quality or workflow counts into incident truth.",
        "Se conciliaron el historial operativo acotado y la evidencia de incidentes aportada sin convertir el volumen de actividad en calidad ni los conteos de flujos de trabajo en verdad sobre incidentes.",
    ),
    (
        "Address material security/assurance issues, highest exact-source maintainability risks, and decision-blocking evidence gaps.",
        "Abordar los problemas materiales de seguridad y aseguramiento, los mayores riesgos de mantenibilidad con fuente exacta y las brechas de evidencia que bloquean decisiones.",
    ),
    (
        "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.",
        "Reforzar los límites de arquitectura, la automatización de pruebas y publicaciones, la evidencia de QA funcional y la verificación de remediaciones.",
    ),
    (
        "Resolve remaining architectural debt, platform/runtime evidence gaps, and supplied stakeholder/requirements objectives.",
        "Resolver la deuda arquitectónica restante, las brechas de evidencia de plataforma y ejecución y los objetivos aportados de partes interesadas y requisitos.",
    ),
    (
        "The existing 0-30/31-90/91-180 roadmap framework was drafted from technical priorities, evidence gaps, supplied requirements, and supplied constraints without creating commitments.",
        "El marco existente de hoja de ruta de 0-30/31-90/91-180 días se redactó a partir de prioridades técnicas, brechas de evidencia, requisitos aportados y restricciones aportadas, sin crear compromisos.",
    ),
    ("security triage, residual risk, remediation verification", "triaje de seguridad, riesgo residual, verificación de remediación"),
    ("Architecture / senior engineering", "Arquitectura / ingeniería sénior"),
    ("architecture boundaries, maintainability, complex remediation", "límites de arquitectura, mantenibilidad, remediación compleja"),
    ("CI/CD, deployment, observability, release controls", "CI/CD, despliegue, observabilidad, controles de publicación"),
    ("functional QA, platform parity, acceptance evidence", "QA funcional, paridad de plataformas, evidencia de aceptación"),
    (
        "Role and skill categories were derived from the technical roadmap without inventing salaries, rates, vendors, contracts, or budgets.",
        "Las categorías de roles y habilidades se derivaron de la hoja de ruta técnica sin inventar salarios, tarifas, proveedores, contratos ni presupuestos.",
    ),
    (
        "Evidence-backed priorities, quick wins, roadmap/resourcing context, and missing-evidence limits were condensed automatically for executive review.",
        "Las prioridades basadas en evidencia, los logros rápidos, el contexto de hoja de ruta y recursos y los límites por evidencia faltante se resumieron automáticamente para la revisión ejecutiva.",
    ),
)

_LABEL_ONLY = {
    "Assessment-wide",
    "Control",
    "Customer",
    "Evidence",
    "Findings",
    "Generated",
    "Impact",
    "Level",
    "Maturity",
    "Project",
    "Recommendation",
    "Repository",
    "Score",
    "Service",
    "Status",
    "Summary",
    "Title",
    "Value",
    "Window",
    "unavailable",
}

_LITERAL_MARKDOWN_RE = re.compile(
    r"(?ms)(^```[^\n]*\n.*?^```\s*$|^~~~[^\n]*\n.*?^~~~\s*$)"
)
_INLINE_LITERAL_RE = re.compile(r"(`[^`\n]+`|<!--.*?-->)", re.S)
_LOCAL_PAGE_LABEL = re.compile(r"^Page\s+\d+$", re.IGNORECASE)
_PRESENTATION_PROSE_FIELDS = {
    "acceptance_criteria",
    "business_impact",
    "can_conclude",
    "cannot_conclude",
    "decision",
    "description",
    "evidence",
    "evidence_to_resolve",
    "exit_criteria",
    "fact",
    "findings",
    "focus",
    "impact",
    "interpretation",
    "label",
    "limitations",
    "objective",
    "recommendation",
    "recommended_correction",
    "required_input",
    "rollback",
    "score_rationale",
    "summary",
    "title",
    "unavailable",
    "unavailable_data_notes",
    "verification",
    "why_it_matters",
}
_RAW_CANONICAL_SUBTREES = {
    "candidate_register",
    "canonical_findings",
    "canonical_scanner_finding_register",
    "client_finding_remediation_register",
    "raw_findings",
    "scanner",
    "scanner_execution_records",
}
_ENGLISH_PRESENTATION_SIGNAL = re.compile(
    r"\b(?:the|and|or|is|are|was|were|with|without|from|at|before|after|until|while|"
    r"remain|remains|required|requires|require|reviewed|verified|analyzed|completed|"
    r"pending|only|against|into|should|must|cannot|could|would|has|have|does|did|not|"
    r"available|unavailable|missing|failed|blocked|retained|supplied|approved|authorized|"
    r"disabled|verification|workflow|assessed|complexity|hotspot|reduce)\b",
    re.IGNORECASE,
)


def _looks_like_untranslated_english(value: str) -> bool:
    text = str(value or "").strip()
    if not text or len(re.findall(r"[A-Za-z]+", text)) < 3:
        return False
    if re.fullmatch(r"[A-Za-z0-9_.:/@+-]+", text):
        return False
    if re.search(r"(?:^|\s)(?:https?://|[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)", text):
        # A path or URL alone is immutable evidence. A surrounding sentence still
        # has enough English signals to be caught by the count below.
        without_literals = re.sub(
            r"https?://\S+|[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+",
            "",
            text,
        )
    else:
        without_literals = text
    return len(_ENGLISH_PRESENTATION_SIGNAL.findall(without_literals)) >= 2


def _maturity_level_es(value: str) -> str:
    raw = str(value or "").strip()
    return {
        "exceptional": "Excepcional",
        "strong": "Sólido",
        "senior": "Senior",
        "moderate": "Moderado",
        "mid": "Intermedio",
        "junior": "Junior",
        "pending": "Pendiente",
        "not scored": "Sin puntuación",
    }.get(raw.casefold(), raw)


_SCANNER_STATUS_ES = {
    "blocked": "bloqueada",
    "complete": "completada",
    "completed": "completada",
    "completed_clean": "completada sin hallazgos",
    "completed_with_findings": "completada con hallazgos",
    "error": "con error",
    "failed": "fallida",
    "missing": "faltante",
    "not_applicable": "no aplicable",
    "partial": "parcial",
    "passed": "aprobada",
    "pending": "pendiente",
    "skipped": "omitida",
    "timed_out": "con tiempo agotado",
    "timeout": "con tiempo agotado",
    "unavailable": "no disponible",
    "unknown": "desconocida",
}

_SCANNER_VERIFICATION_DEFICIT_ES = {
    "completion requirements were not met": (
        "no se cumplieron los requisitos de finalización"
    ),
    "current_run_not_proven": (
        "no se demostró que perteneciera a la ejecución actual"
    ),
    "execution_not_observed_for_this_report": (
        "no se observó la ejecución para este informe"
    ),
    "exact_commit_match_not_proven": (
        "no se demostró la coincidencia con el commit exacto"
    ),
    "scanner_verification_not_proven": (
        "no se demostró la verificación del analizador"
    ),
    "complete_artifact_capture_not_proven": (
        "no se demostró la captura completa del artefacto"
    ),
    "artifact_hash_missing": "falta el hash del artefacto",
    "full_git_history_not_verified": "no se verificó el historial Git completo",
    "No exact-SHA current-run scanner record was retained.": (
        "No se conservó ningún registro del analizador de la ejecución actual "
        "para el SHA exacto."
    ),
}

_CI_OUTCOME_CLASS_ES = {
    "active_not_historical": "activas no históricas",
    "cancelled": "canceladas",
    "expected_or_unclassified_cancellation": (
        "cancelaciones esperadas o sin clasificar"
    ),
    "genuine_failure": "fallos reales",
    "infrastructure_fault": "fallos de infraestructura",
    "manual_cancellation": "cancelaciones manuales",
    "neutral_or_skipped": "neutrales u omitidas",
    "success": "exitosas",
    "superseded_cancellation": "cancelaciones sustituidas",
    "unknown_review_required": "desconocidas que requieren revisión",
}

_REQUIRED_CHECK_HEALTH_ES = {
    "green": "en verde",
    "not_green": "no verde",
    "not_observed": "no observado",
    "unknown": "desconocido",
    "unavailable": "no disponible",
}


def _ci_outcome_classes_es(match: re.Match[str]) -> str:
    raw_classes = match.group("classes").strip()
    if raw_classes == "No classified workflow outcomes retained":
        return (
            "Clases de resultados de los flujos de trabajo: no se conservaron "
            "resultados clasificados"
        )
    translated: list[str] = []
    for raw_item in raw_classes.split(";"):
        key, separator, value = raw_item.strip().partition("=")
        if (
            not separator
            or key not in _CI_OUTCOME_CLASS_ES
            or not value.strip().isdigit()
        ):
            raise ValueError(
                f"missing Spanish CI outcome translation: {raw_item.strip()[:180]}"
            )
        translated.append(f"{_CI_OUTCOME_CLASS_ES[key]}={value.strip()}")
    return "Clases de resultados de los flujos de trabajo: " + "; ".join(translated)


def _required_check_health_es(match: re.Match[str]) -> str:
    status = match.group("status").strip()
    translated = _REQUIRED_CHECK_HEALTH_ES.get(status.casefold())
    if translated is None:
        raise ValueError(
            f"missing Spanish required-check health translation: {status[:120]}"
        )
    return (
        "Estado de las verificaciones requeridas del commit evaluado: "
        f"{translated} (commit {match.group('commit')})."
    )


def _historical_failure_rate_es(match: re.Match[str]) -> str:
    rate = match.group("rate").strip()
    rendered = (
        "no disponible"
        if rate.casefold() in {"none", "null", "unavailable", "not available"}
        else rate
    )
    return f"Tasa histórica de fallos reales: {rendered}"


def _scanner_execution_line_es(match: re.Match[str]) -> str:
    status = match.group("status")
    translated_status = _SCANNER_STATUS_ES.get(status.casefold())
    if translated_status is None:
        raise ValueError(
            f"missing Spanish scanner status translation: {status[:120]}"
        )
    artifact_hash = match.group("artifact_hash")
    rendered_hash = (
        "no disponible"
        if artifact_hash.casefold() == "unavailable"
        else artifact_hash
    )
    current_run = match.group("current_run")
    current_run_line = (
        "ejecución_actual=" + ("sí" if current_run == "True" else "no") + "; "
        if current_run is not None
        else ""
    )
    return (
        f"{match.group('scanner')}: estado={translated_status}; "
        f"{current_run_line}"
        "coincidencia_commit_exacto="
        f"{'sí' if match.group('exact') == 'True' else 'no'}; "
        "verificación_completa="
        f"{'sí' if match.group('verified') == 'True' else 'no'}; "
        f"hallazgos={match.group('findings')}; hash_artefacto={rendered_hash}"
    )


def _scanner_limitation_es(match: re.Match[str]) -> str:
    scanner = match.group("scanner")
    status = match.group("status").strip()
    reason = match.group("reason").strip()
    translated_status = _SCANNER_STATUS_ES.get(status.casefold())
    if translated_status is None:
        raise ValueError(
            f"missing Spanish scanner status translation: {status[:120]}"
        )
    translated_reasons: list[str] = []
    for raw_clause in reason.split(";"):
        clause = raw_clause.strip()
        status_clause = re.fullmatch(
            r"status=(?P<status>[A-Za-z0-9_.+-]+)",
            clause,
        )
        if status_clause is not None:
            raw_status = status_clause.group("status")
            clause_status = _SCANNER_STATUS_ES.get(raw_status.casefold())
            if clause_status is not None:
                translated_reasons.append(
                    "estado=" + clause_status
                )
                continue
        missing_binary = re.fullmatch(
            r"(?P<binary>[A-Za-z0-9_.+-]+)(?: binary)? is not installed in "
            r"(?:the|this) worker image\.?",
            clause,
        )
        if missing_binary is not None:
            translated_reasons.append(
                f"{missing_binary.group('binary')} no está instalado en la imagen "
                "del entorno de ejecución"
            )
            continue
        translated_clause = _SCANNER_VERIFICATION_DEFICIT_ES.get(clause)
        if translated_clause is None:
            translated_reasons.append(f"detalle técnico original: {clause}")
        else:
            translated_reasons.append(translated_clause)
    return (
        f"La evidencia de {scanner} para el SHA exacto permanece "
        f"{translated_status}: "
        + "; ".join(translated_reasons)
    )


def _repository_unavailable_note_es(match: re.Match[str]) -> str:
    label = match.group("label")
    exact_labels = {
        "Captured-commit recursive file tree": (
            "El árbol recursivo de archivos del commit capturado"
        ),
        "Captured-commit root listing": "El listado raíz del commit capturado",
        "Commit history": "El historial de commits",
        "Complexity source evidence": "La evidencia de código fuente para complejidad",
        "GitHub deployment evidence": "La evidencia de despliegues de GitHub",
        "Pull-request history": "El historial de solicitudes de incorporación",
        "Repository file-profile evidence": (
            "La evidencia del perfil de archivos del repositorio"
        ),
        "Repository metadata": "La evidencia de metadatos del repositorio",
        "Workflow file evidence": "La evidencia de archivos de flujos de trabajo",
        "Workflow-run history": "El historial de ejecuciones de flujos de trabajo",
    }
    translated_label = exact_labels.get(label)
    if translated_label is None and label.startswith("Captured-commit file "):
        translated_label = (
            "El archivo del commit capturado "
            + label.removeprefix("Captured-commit file ")
        )
    if translated_label is None and label.startswith("Captured-commit workflow "):
        translated_label = (
            "El flujo de trabajo del commit capturado "
            + label.removeprefix("Captured-commit workflow ")
        )
    if translated_label is None and label.startswith("Workflow jobs for run "):
        translated_label = (
            "La evidencia de trabajos del flujo de trabajo de la ejecución "
            + label.removeprefix("Workflow jobs for run ")
        )
    if translated_label is None and label.startswith("Deployment status for "):
        translated_label = (
            "El estado del despliegue "
            + label.removeprefix("Deployment status for ")
        )
    if translated_label is None:
        raise ValueError(
            f"missing Spanish repository evidence label translation: {label[:180]}"
        )

    reason = match.group("reason")
    translated_reason = {
        "because the GitHub credential or installation lacks required read access": (
            "porque la credencial o instalación de GitHub carece del acceso de "
            "lectura requerido"
        ),
        "through the authorized GitHub API scope": (
            "mediante el alcance autorizado de la API de GitHub"
        ),
        "through the authorized GitHub API scope; verify repository access": (
            "mediante el alcance autorizado de la API de GitHub; verifique el "
            "acceso al repositorio"
        ),
        "because the GitHub API rate limit was reached": (
            "porque se alcanzó el límite de solicitudes de la API de GitHub"
        ),
        "through the GitHub API": "mediante la API de GitHub",
    }.get(reason)
    if translated_reason is None:
        raise ValueError(
            f"missing Spanish repository evidence reason translation: {reason[:180]}"
        )
    return f"{translated_label} no estaba disponible {translated_reason}."


def _structured_presentation_es(value: str) -> str | None:
    match = re.fullmatch(
        r"Actionable hotspot (?P<path>[^\r\n]+?):(?P<line>\d+) · "
        r"(?P<name>[^\r\n]+?) · complexity (?P<complexity>\d+)\.",
        value,
    )
    if match is not None:
        return (
            f"Punto crítico accionable {match.group('path')}:"
            f"{match.group('line')} · {match.group('name')} · "
            f"complejidad {match.group('complexity')}."
        )

    match = re.fullmatch(
        r"Decompose the highest-complexity modules first, beginning with "
        r"(?P<modules>.+?), and add characterization tests plus CI complexity "
        r"thresholds\.",
        value,
    )
    if match is not None:
        return (
            "Descomponer primero los módulos de mayor complejidad, comenzando por "
            f"{match.group('modules')}, y agregar pruebas de caracterización y "
            "umbrales de complejidad en CI."
        )

    match = re.fullmatch(
        r"(?P<scanner>[A-Za-z0-9_.+-]+): status=(?P<status>[A-Za-z0-9_-]+); "
        r"(?:current_run=(?P<current_run>True|False); )?"
        r"exact_commit_match=(?P<exact>True|False); "
        r"verified_complete=(?P<verified>True|False); "
        r"findings=(?P<findings>\d+); artifact_hash=(?P<artifact_hash>[^\s;]+)",
        value,
    )
    if match is not None:
        return _scanner_execution_line_es(match)

    match = re.fullmatch(
        r"scanner_execution_records\[(?P<index>\d+)\]\.failure_reason: "
        r"(?P<tool>[A-Za-z0-9_.+-]+)(?: binary)? is not installed in "
        r"(?:the|this) worker image\.?",
        value,
    )
    if match is not None:
        return (
            "scanner_execution_records"
            f"[{match.group('index')}].failure_reason: {match.group('tool')} no está "
            "instalado en la imagen del entorno de ejecución."
        )

    match = re.fullmatch(
        r"(?P<scanner>[A-Za-z0-9_.+-]+) exact-SHA evidence remains "
        r"(?P<status>[A-Za-z0-9_-]+): (?P<reason>[^\r\n]+)",
        value,
    )
    if match is not None:
        return _scanner_limitation_es(match)

    match = re.fullmatch(
        r"Workflow outcome classes: (?P<classes>"
        r"No classified workflow outcomes retained|"
        r"[a-z_]+=\d+(?:; [a-z_]+=\d+)*)(?:\.)?",
        value,
    )
    if match is not None:
        return _ci_outcome_classes_es(match) + "."

    match = re.fullmatch(
        r"Historical genuine-failure rate: "
        r"(?P<rate>None|null|unavailable|not available|\d+(?:\.\d+)?)(?:\.)?",
        value,
    )
    if match is not None:
        return _historical_failure_rate_es(match)

    match = re.fullmatch(
        r"Classified CI history retains genuine_failures=(?P<genuine>\d+), "
        r"infrastructure_faults=(?P<infra>\d+), and "
        r"unknown_review_required=(?P<unknown>\d+)\.",
        value,
    )
    if match is not None:
        return (
            "El historial clasificado de CI conserva "
            f"fallos reales={match.group('genuine')}, fallos de infraestructura="
            f"{match.group('infra')} y resultados desconocidos que requieren revisión="
            f"{match.group('unknown')}."
        )

    match = re.fullmatch(
        r"Assessed-commit required-check health: (?P<status>[A-Za-z0-9_-]+) "
        r"\(commit (?P<commit>[^)]+)\)\.",
        value,
    )
    if match is not None:
        return _required_check_health_es(match)

    match = re.fullmatch(
        r"Current default-branch required-check health: "
        r"(?P<health>True|False|not observed)\.",
        value,
    )
    if match is not None:
        return (
            "Estado de las verificaciones requeridas de la rama predeterminada actual: "
            + {
                "True": "en verde",
                "False": "no verde",
                "not observed": "no observado",
            }[match.group("health")]
            + "."
        )

    match = re.fullmatch(
        r"Source-reviewed analyzer dispositions: (?P<count>\d+) bounded "
        r"nonblocking record\(s\); full rationale retained in canonical JSON\.",
        value,
    )
    if match is not None:
        record = (
            "registro acotado no bloqueante"
            if int(match.group("count")) == 1
            else "registros acotados no bloqueantes"
        )
        return (
            "Disposiciones de analizadores revisadas en el código fuente: "
            f"{match.group('count')} {record}; la "
            "justificación completa se conserva en el JSON canónico."
        )

    match = re.fullmatch(r"Unique classified hotspots: (?P<count>\d+)\.", value)
    if match is not None:
        return f"Puntos críticos únicos clasificados: {match.group('count')}."

    match = re.fullmatch(
        r"Actionable production/report hotspots at complexity >=30: "
        r"(?P<count>\d+)\.",
        value,
    )
    if match is not None:
        return (
            "Puntos críticos accionables de producción o generación de informes "
            f"con complejidad >=30: {match.group('count')}."
        )

    match = re.fullmatch(
        r"Classification counts: (?P<counts>\{[^\r\n]*\})\.",
        value,
    )
    if match is not None:
        return f"Conteos por clasificación: {match.group('counts')}."

    match = re.fullmatch(
        r"Raw high-complexity region count retained for audit: (?P<count>\d+)\.",
        value,
    )
    if match is not None:
        return (
            "Conteo sin procesar de regiones de alta complejidad conservado para "
            f"auditoría: {match.group('count')}."
        )

    match = re.fullmatch(
        r"Technical maturity remains based on exact-commit technical controls\. "
        r"Evidence-Adjusted readiness is (?P<adjusted>\d+(?:\.\d+)?)/100 versus "
        r"technical maturity (?P<technical>\d+(?:\.\d+)?)/100\. NICO retains "
        r"(?P<review>\d+) review-required candidates and (?P<material>\d+) "
        r"confirmed material findings as explicit review context\. Candidate volume, "
        r"clustering and reviewer workload do not change numeric security or "
        r"readiness scores\.",
        value,
    )
    if match is not None:
        return (
            "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
            f"La preparación ajustada por evidencia es {match.group('adjusted')}/100 "
            f"frente a una madurez técnica de {match.group('technical')}/100. NICO "
            f"conserva {match.group('review')} candidatos que requieren revisión y "
            f"{match.group('material')} hallazgos materiales confirmados como contexto "
            "explícito de revisión. El volumen de candidatos, la agrupación y la carga "
            "de trabajo de revisión no modifican las puntuaciones numéricas de "
            "seguridad ni de preparación."
        )

    match = re.fullmatch(
        r"(?P<count>\d+) grouped static-analysis candidates require validation",
        value,
    )
    if match is not None:
        return (
            f"{match.group('count')} "
            + (
                "candidato agrupado de análisis estático requiere validación"
                if int(match.group("count")) == 1
                else "candidatos agrupados de análisis estático requieren validación"
            )
        )

    match = re.fullmatch(
        r"(?P<count>\d+) (?P<profile>captured-commit|repository) profile item\(s\) "
        r"were unavailable; "
        r"complexity coverage is limited to readable sampled files\.",
        value,
    )
    if match is not None:
        singular = int(match.group("count")) == 1
        item = "elemento" if singular else "elementos"
        availability = "no estaba disponible" if singular else "no estaban disponibles"
        profile = (
            "del commit capturado"
            if match.group("profile") == "captured-commit"
            else "del repositorio"
        )
        return (
            f"{match.group('count')} {item} del perfil {profile} "
            f"{availability}; la cobertura de complejidad se limita a archivos "
            "muestreados legibles."
        )

    match = re.fullmatch(
        r"(?P<count>\d+) Python source file\(s\) could not be parsed and were "
        r"excluded from complexity metrics\.",
        value,
    )
    if match is not None:
        singular = int(match.group("count")) == 1
        source_file = (
            "archivo de código fuente Python"
            if singular
            else "archivos de código fuente Python"
        )
        return (
            f"No se {'pudo' if singular else 'pudieron'} analizar "
            f"{match.group('count')} {source_file} y se "
            f"{'excluyó' if singular else 'excluyeron'} de las métricas de complejidad."
        )

    match = re.fullmatch(
        r"(?P<count>\d+) source parser limitation\(s\) were retained in the "
        r"architecture evidence\.",
        value,
    )
    if match is not None:
        singular = int(match.group("count")) == 1
        limitation = "limitación" if singular else "limitaciones"
        return (
            f"Se {'conservó' if singular else 'conservaron'} {match.group('count')} "
            f"{limitation} del analizador de "
            "código fuente en la evidencia de arquitectura."
        )

    match = re.fullmatch(
        r"(?P<label>Captured-commit recursive file tree|Captured-commit root "
        r"listing|Captured-commit file [^\r\n]+|Captured-commit workflow [^\r\n]+|"
        r"Commit history|Complexity source evidence|Deployment status for [^\r\n]+|"
        r"GitHub deployment evidence|Pull-request history|Repository file-profile "
        r"evidence|Repository metadata|Workflow file evidence|Workflow jobs for run "
        r"[^\r\n]+|Workflow-run history) (?:was|were) unavailable "
        r"(?P<reason>because the GitHub credential or installation lacks required "
        r"read access|through the authorized GitHub API scope(?:; verify repository "
        r"access)?|because the GitHub API rate limit was reached|through the GitHub "
        r"API)\.",
        value,
    )
    if match is not None:
        return _repository_unavailable_note_es(match)

    match = re.fullmatch(
        r"Workflow jobs for run (?P<run_id>[^\r\n]+) were returned without a "
        r"jobs list\.",
        value,
    )
    if match is not None:
        return (
            "La evidencia de trabajos del flujo de trabajo de la ejecución "
            f"{match.group('run_id')} se devolvió sin una lista de trabajos."
        )

    match = re.fullmatch(
        r"GitHub deployment evidence: observed=(?P<observed>\d+), "
        r"success=(?P<success>\d+), non-success=(?P<non_success>\d+)\.",
        value,
    )
    if match is not None:
        return (
            "Evidencia de despliegues de GitHub: "
            f"observados={match.group('observed')}, exitosos={match.group('success')}, "
            f"no exitosos={match.group('non_success')}."
        )

    match = re.fullmatch(
        r"OSV lookup returned HTTP (?P<status>\d{3}); dependency vulnerability "
        r"status is incomplete\.",
        value,
    )
    if match is not None:
        return (
            f"La consulta a OSV devolvió HTTP {match.group('status')}; el estado de "
            "vulnerabilidades de dependencias está incompleto."
        )

    match = re.fullmatch(
        r"OSV lookup unavailable: (?P<detail>[^\r\n]+)",
        value,
    )
    if match is not None:
        return (
            "La consulta a OSV no estaba disponible; detalle técnico original: "
            f"{match.group('detail')}"
        )

    match = re.fullmatch(
        r"OSV returned (?P<count>\d+) vulnerability record\(s\) for "
        r"(?P<ecosystem>[A-Za-z0-9_.-]+):(?P<package>[^\s]+)@"
        r"(?P<version>[^:\s]+): (?P<ids>[^\r\n]+)\.",
        value,
    )
    if match is not None:
        record = (
            "registro de vulnerabilidad"
            if int(match.group("count")) == 1
            else "registros de vulnerabilidades"
        )
        return (
            f"OSV devolvió {match.group('count')} {record} para "
            f"{match.group('ecosystem')}:{match.group('package')}@"
            f"{match.group('version')}: {match.group('ids')}."
        )

    match = re.fullmatch(
        r"OSV returned no vulnerability records for (?P<count>\d+) pinned "
        r"dependency query/queries\.",
        value,
    )
    if match is not None:
        query = "consulta" if int(match.group("count")) == 1 else "consultas"
        return (
            "OSV no devolvió registros de vulnerabilidades para "
            f"{match.group('count')} {query} de dependencias con versión fijada."
        )

    match = re.fullmatch(
        r"Exact-SHA source archive profiling was unavailable: "
        r"(?P<exception>[A-Za-z_][A-Za-z0-9_.]*)\. Existing bounded file evidence "
        r"remains visible\.",
        value,
    )
    if match is not None:
        return (
            "El perfilado del archivo de código fuente del SHA exacto no estaba "
            f"disponible: {match.group('exception')}. La evidencia acotada de "
            "archivos existente sigue visible."
        )

    match = re.fullmatch(
        r"(?P<path>(?:(?:[A-Za-z0-9_-]+\.)+unavailable_data_notes\[\d+\]|"
        r"snapshot\.guardrail)): "
        r"(?P<note>[^\r\n]+)",
        value,
    )
    if match is not None:
        translated_note = _translate_presentation_field(
            match.group("note"),
            "unavailable",
        )
        return (
            f"{match.group('path')}: {translated_note}"
        )

    structural_prefixes = (
        "Actionable hotspot ",
        "Actionable production/report hotspots",
        "Assessed-commit required-check health:",
        "Captured-commit ",
        "Classification counts:",
        "Classified CI history retains ",
        "Commit history",
        "Complexity source evidence",
        "Current default-branch required-check health:",
        "Deployment status for ",
        "GitHub deployment evidence",
        "Exact-SHA source archive",
        "Historical genuine-failure rate:",
        "JavaScript and TypeScript complexity",
        "No eligible first-party source files",
        "No eligible source files",
        "No workflow files",
        "Pull-request history",
        "Raw high-complexity region count retained for audit:",
        "Repository file-profile evidence",
        "Repository metadata",
        "Scanner evidence is not client-ready",
        "Snapshot-bound repository evidence",
        "Source-reviewed analyzer dispositions:",
        "Technical maturity remains based on exact-commit technical controls.",
        "TypeScript compiler AST evidence",
        "Unique classified hotspots:",
        "Workflow file evidence",
        "Workflow outcome classes:",
        "Workflow jobs for run ",
        "Workflow-run history",
        "OSV lookup ",
        "OSV returned ",
    )
    if value.startswith(structural_prefixes) or re.match(
        r"^(?:\d+ (?:(?:captured-commit|repository) profile item|grouped static-analysis "
        r"candidates require validation|Python source file|source parser limitation)|"
        r"[A-Za-z0-9_.+-]+: status=|"
        r"(?:[A-Za-z0-9_-]+\.)+unavailable_data_notes\[\d+\]|snapshot\.guardrail|"
        r"scanner_execution_records\[\d+\]\.failure_reason:|"
        r"[A-Za-z0-9_.+-]+ exact-SHA evidence remains )",
        value,
    ):
        raise ValueError(
            f"unrecognized Spanish presentation contract: {value[:180]}"
        )
    return None


def _translate_presentation_field(value: str, key: str) -> str:
    stripped = str(value or "").strip()
    has_exact_translation = _CANONICAL_PARITY_EXACT.get(
        stripped,
        _ES_EXTRA_EXACT.get(stripped, ES_EXACT.get(stripped)),
    ) is not None
    preserves_validated_opaque_fields = (
        not has_exact_translation
        and "\n" not in stripped
        and "\r" not in stripped
        and _structured_presentation_es(stripped) is not None
    )
    translated = _translate_presentation(value)
    if (
        key in _PRESENTATION_PROSE_FIELDS
        and _looks_like_untranslated_english(translated)
        and not preserves_validated_opaque_fields
    ):
        raise ValueError(
            f"missing Spanish presentation translation for {key}: {str(value or '')[:180]}"
        )
    return translated


def _translate_presentation(value: Any) -> str:
    text = str(value or "")
    if "\n" in text or "\r" in text:
        return "".join(
            segment
            if segment in {"\n", "\r", "\r\n"}
            else _translate_presentation(segment)
            for segment in re.split(r"(\r\n|\r|\n)", text)
            if segment != ""
        )
    stripped = text.strip()
    exact = _CANONICAL_PARITY_EXACT.get(
        stripped,
        _ES_EXTRA_EXACT.get(stripped, ES_EXACT.get(stripped)),
    )
    if exact is not None:
        return text.replace(stripped, exact, 1)
    structured = _structured_presentation_es(stripped)
    if structured is not None:
        return text.replace(stripped, structured, 1)
    text = re.sub(
        r"Core technical evidence for (.+?) at (.+?) produced an evidence-bound (.+?) maturity signal \((\d+)/100\)\. Comprehensive-only modules continue after this score and remain subject to human review\.",
        lambda match: (
            f"La evidencia técnica principal de {match.group(1)} en {match.group(2)} produjo una señal "
            f"de madurez basada en evidencia de nivel {_maturity_level_es(match.group(3))} ({match.group(4)}/100). Los módulos "
            "exclusivos de la evaluación integral continúan después de esta puntuación y siguen sujetos a revisión humana."
        ),
        text,
    )
    text = re.sub(
        r"Exact-SHA technical evidence for (.+?) produced an evidence-bound (.+?) maturity signal \((\d+)/100\) and independently evidence-adjusted score of (\d+)/100\. No score was raised without retained evidence\.",
        lambda match: (
            f"La evidencia técnica del SHA exacto de {match.group(1)} produjo una señal de madurez "
            f"basada en evidencia de nivel {_maturity_level_es(match.group(2))} ({match.group(3)}/100) y una puntuación independiente "
            f"ajustada por evidencia de {match.group(4)}/100. No se elevó ninguna puntuación sin evidencia conservada."
        ),
        text,
    )
    text = re.sub(
        r"Exact-SHA technical evidence for (.+?) produced an evidence-bound (.+?) maturity signal \((\d+)/100\) and evidence-adjusted score of (\d+)/100\. Mutable operational history is disclosed separately and cannot change the score for this immutable commit\.",
        lambda match: (
            f"La evidencia técnica del SHA exacto de {match.group(1)} produjo una señal de madurez "
            f"basada en evidencia de nivel {_maturity_level_es(match.group(2))} ({match.group(3)}/100) y una puntuación ajustada por evidencia "
            f"de {match.group(4)}/100. El historial operativo mutable se declara por separado y no puede cambiar "
            "la puntuación de este commit inmutable."
        ),
        text,
    )
    text = re.sub(
        r"Exact-SHA technical evidence for (.+?) produced an evidence-bound (.+?) maturity signal \((\d+)/100\) and evidence-adjusted readiness of (\d+)/100\. Only verified material findings and incomplete applicable analyzers affect technical scores; unverified candidate volume affects assurance only\.",
        lambda match: (
            f"La evidencia técnica del SHA exacto de {match.group(1)} produjo una señal de madurez "
            f"basada en evidencia de nivel {_maturity_level_es(match.group(2))} ({match.group(3)}/100) y una preparación ajustada por evidencia "
            f"de {match.group(4)}/100. Solo los hallazgos materiales verificados y los analizadores aplicables "
            "incompletos afectan las puntuaciones técnicas; el volumen de candidatos no verificados afecta únicamente el aseguramiento."
        ),
        text,
    )
    text = re.sub(
        r"Exact-SHA technical maturity is (\d+)/100\. Evidence-adjusted readiness is (\d+)/100 after bounded penalties for unresolved candidate volume, missing raw candidate payloads, and incomplete applicable analyzers\. Unresolved candidates are not presented as confirmed defects\.",
        lambda match: (
            f"La madurez técnica del SHA exacto es {match.group(1)}/100. La preparación ajustada por evidencia "
            f"es {match.group(2)}/100 después de aplicar penalizaciones acotadas por el volumen de candidatos sin "
            "resolver, la ausencia de cargas sin procesar y los analizadores aplicables incompletos. Los candidatos "
            "sin resolver no se presentan como defectos confirmados."
        ),
        text,
    )
    text = re.sub(
        r"Static Analysis is scored (\d+)/100 from completed analyzer evidence\. Analyzer execution coverage is (\d+)%; remaining failed or partial tools are shown separately as Review Limited assurance\.",
        lambda match: (
            f"El análisis estático recibe una puntuación de {match.group(1)}/100 a partir de evidencia de analizadores completados. "
            f"La cobertura de ejecución de analizadores es del {match.group(2)} %; las herramientas fallidas o parciales restantes "
            "se muestran por separado con aseguramiento de revisión limitada."
        ),
        text,
    )
    text = re.sub(
        r"A bounded technical score of (\d+)/100 is supported by completed exact-snapshot Semgrep and TypeScript evidence, (\d+)% accepted applicable-analyzer coverage, and no retained verified critical or high-severity blocker\. Incomplete analyzers constrain assurance independently and do not erase the completed analyzer evidence\.",
        lambda match: (
            f"Una puntuación técnica acotada de {match.group(1)}/100 está respaldada por evidencia completada de Semgrep y TypeScript "
            f"para la instantánea exacta, una cobertura aceptada del {match.group(2)} % de analizadores aplicables y la ausencia de un "
            "bloqueador crítico o de alta gravedad verificado y conservado. Los analizadores incompletos limitan el aseguramiento de forma "
            "independiente y no eliminan la evidencia de analizadores completados."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) (verified material|review required|approved or nonblocking|excluded test only) scanner candidate\(s\) were retained by count, but their raw payloads were unavailable to the canonical finding register\.",
        lambda match: (
            f"Se conservaron por conteo {match.group(1)} "
            f"{'candidato de analizador' if int(match.group(1)) == 1 else 'candidatos de analizadores'}, "
            "con disposición "
            + {
                "verified material": "de hallazgo material verificado",
                "review required": "de revisión requerida",
                "approved or nonblocking": "aprobada o no bloqueante",
                "excluded test only": "excluida por ser solo de pruebas",
            }[match.group(2)]
            + ", pero sus cargas sin procesar no estaban disponibles para el registro canónico de hallazgos."
        ),
        text,
    )
    text = re.sub(
        r"Jobs observed:\s*(\d+); success rate:\s*([^.]+)\.",
        r"Trabajos observados: \1; tasa de éxito: \2.",
        text,
    )
    text = re.sub(
        r"Prior candidate register imported from exact commit (.+?); assessment-subject match=(True|False) \((.+?)\)\.",
        lambda match: (
            f"Registro previo de candidatos importado del commit exacto {match.group(1)}; "
            f"coincidencia del sujeto de evaluación={'sí' if match.group(2) == 'True' else 'no'} "
            f"({match.group(3)})."
        ),
        text,
    )
    text = re.sub(
        r"Prior candidates: (\d+); current candidates: (\d+)\.",
        r"Candidatos previos: \1; candidatos actuales: \2.",
        text,
    )
    text = re.sub(
        r"Exact carry-forward: (\d+); location-changed: (\d+); evidence-changed: (\d+)\.",
        r"Arrastre exacto: \1; ubicación modificada: \2; evidencia modificada: \3.",
        text,
    )
    text = re.sub(
        r"Newly observed: (\d+); no longer observed: (\d+)\.",
        r"Observados por primera vez: \1; ya no observados: \2.",
        text,
    )
    text = re.sub(
        r"Non-partitioning NICO placeholder identities were normalized as unsupplied before lineage comparison: (.+?)\. Real project, workspace, and target identities remain fail-closed partitioning boundaries\.",
        r"Las identidades de marcador de NICO que no particionan se normalizaron como no suministradas antes de comparar el linaje: \1. Las identidades reales de proyecto, espacio de trabajo y objetivo siguen siendo límites de partición de cierre seguro.",
        text,
    )
    text = re.sub(
        r"Technical triage proposals imported for (\d+) current candidate\(s\)\.",
        lambda match: (
            f"Propuestas de triaje técnico importadas para {match.group(1)} "
            f"{'candidato actual' if int(match.group(1)) == 1 else 'candidatos actuales'}."
        ),
        text,
    )
    text = re.sub(
        r"Technical triage outcome totals: not_actionable=(\d+), needs_review=(\d+), confirmed=(\d+)\.",
        r"Totales de resultados del triaje técnico: no accionables=\1, requieren revisión=\2, confirmados=\3.",
        text,
    )
    text = re.sub(
        r"Current-evidence candidates requiring new technical triage: (\d+); fresh automated triage completed=(\d+)\.",
        r"Candidatos de la evidencia actual que requieren nuevo triaje técnico: \1; nuevo triaje automatizado completado=\2.",
        text,
    )
    text = re.sub(
        r"Technical triage coverage: (\d+)/(\d+) \(([^)]+)%\)\.",
        r"Cobertura de triaje técnico: \1/\2 (\3 %).",
        text,
    )
    text = re.sub(
        r"Individual human attention: (\d+); grouped-review eligible candidates: (\d+); grouped human-review clusters: (\d+); quality-control pool: (\d+)\.",
        r"Atención humana individual: \1; candidatos elegibles para revisión agrupada: \2; grupos de revisión humana: \3; conjunto de control de calidad: \4.",
        text,
    )
    text = re.sub(
        r"Human review work units: (\d+) from (\d+) candidate-level human-attention observations before deterministic grouping\.",
        r"Unidades de trabajo de revisión humana: \1 a partir de \2 observaciones de atención humana a nivel de candidato antes de la agrupación determinista.",
        text,
    )
    text = re.sub(
        r"Retained prior dependency recommendations revalidated against the current proof-gap contract: (\d+)\.",
        r"Recomendaciones previas de dependencias conservadas y revalidadas contra el contrato actual de brechas de prueba: \1.",
        text,
    )
    for source, target in sorted(
        _PRESENTATION_REPLACEMENTS,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if source in _LABEL_ONLY:
            if text.strip() == source:
                text = text.replace(source, target, 1)
            else:
                text = re.sub(
                    rf"(?<![A-Za-z0-9_]){re.escape(source)}(?=\s*[:=])",
                    target,
                    text,
                )
            continue
        text = _safe_replace(text, source, target)
    text = re.sub(
        r"(\d+) client-review section\(s\) disclose unavailable, limited, framework-only, or stakeholder-dependent evidence\.",
        r"\1 sección(es) de revisión del cliente declaran evidencia no disponible, limitada, de marco o dependiente de las partes interesadas.",
        text,
    )
    text = re.sub(
        r"(\d+) client-review section\(s\) disclose no disponible, limited, framework-only, or stakeholder-dependent evidencia\.",
        r"\1 sección(es) de revisión del cliente declaran evidencia no disponible, limitada, de marco o dependiente de las partes interesadas.",
        text,
    )
    text = re.sub(
        r"(\d+) client-review sección\(es\)",
        r"\1 sección(es) de revisión del cliente",
        text,
    )
    text = re.sub(
        r"(\d+) sección\(es\) de revisión del cliente",
        lambda match: (
            f"{match.group(1)} sección de revisión del cliente"
            if int(match.group(1)) == 1
            else f"{match.group(1)} secciones de revisión del cliente"
        ),
        text,
    )
    text = re.sub(
        r"(\d+) stage\(s\) disclose unavailable or limited evidence\.",
        lambda match: (
            "1 etapa declara evidencia no disponible o limitada."
            if int(match.group(1)) == 1
            else f"{match.group(1)} etapas declaran evidencia no disponible o limitada."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) of (\d+) applicable scanner executions completed\.",
        lambda match: (
            f"{'Se completó' if int(match.group(2)) == 1 else 'Se completaron'} "
            f"{match.group(1)} de {match.group(2)} "
            f"{'ejecución de analizador aplicable' if int(match.group(2)) == 1 else 'ejecuciones de analizadores aplicables'}."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) resulting candidates remain pending human disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'candidato resultante sigue pendiente' if int(match.group(1)) == 1 else 'candidatos resultantes siguen pendientes'} "
            "de disposición humana."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) stage\(s\) remain blocked or unavailable:",
        lambda match: (
            "1 etapa permanece bloqueada o no disponible:"
            if int(match.group(1)) == 1
            else f"{match.group(1)} etapas permanecen bloqueadas o no disponibles:"
        ),
        text,
    )
    text = re.sub(
        r"(\d+) scanner execution record\(s\) completed; (\d+) candidate\(s\) remain pending human triage\. Execution completion does not equal candidate disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'registro de ejecución de analizadores se completó' if int(match.group(1)) == 1 else 'registros de ejecución de analizadores se completaron'}; "
            f"{match.group(2)} "
            f"{'candidato sigue pendiente' if int(match.group(2)) == 1 else 'candidatos siguen pendientes'} "
            "de triaje humano. La finalización de la ejecución no equivale a la disposición de candidatos."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) scanner execution\(s\) remain incomplete\. (\d+) resulting candidates remain pending human disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'ejecución de analizador permanece incompleta' if int(match.group(1)) == 1 else 'ejecuciones de analizadores permanecen incompletas'}. "
            f"{match.group(2)} "
            f"{'candidato resultante sigue pendiente' if int(match.group(2)) == 1 else 'candidatos resultantes siguen pendientes'} "
            "de disposición humana."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) sampled code-risk pattern hit\(s\) require review\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'coincidencia muestreada de patrones de riesgo en el código requiere' if int(match.group(1)) == 1 else 'coincidencias muestreadas de patrones de riesgo en el código requieren'} revisión."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) material scanner finding\(s\) require immediate human disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'hallazgo material de analizadores requiere' if int(match.group(1)) == 1 else 'hallazgos materiales de analizadores requieren'} disposición humana inmediata."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) scanner candidate\(s\) require human triage\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'candidato de analizadores requiere' if int(match.group(1)) == 1 else 'candidatos de analizadores requieren'} triaje humano."
        ),
        text,
    )
    text = re.sub(r"Failed analyzers:\s*(.+?)\.", r"Analizadores fallidos: \1.", text)
    text = re.sub(r"Timed-out analyzers:\s*(.+?)\.", r"Analizadores con tiempo agotado: \1.", text)
    text = re.sub(
        r"Historical workflow evidence includes (\d+) non-success run\(s\)\.",
        lambda match: (
            f"La evidencia histórica de flujos de trabajo incluye {match.group(1)} "
            f"{'ejecución no exitosa' if int(match.group(1)) == 1 else 'ejecuciones no exitosas'}."
        ),
        text,
    )
    text = re.sub(
        r"Riesgo de complejidad:\s*observed;\s*(\d+) exact-source complexity findings remain pending human review\.",
        lambda match: (
            f"Riesgo de complejidad: observado; {match.group(1)} "
            f"{'hallazgo de complejidad con fuente exacta sigue pendiente' if int(match.group(1)) == 1 else 'hallazgos de complejidad con fuente exacta siguen pendientes'} "
            "de revisión humana."
        ),
        text,
    )
    text = re.sub(
        r"Riesgo de complejidad:\s*observado;\s*(\d+) hallazgos de complejidad con fuente exacta siguen pendientes de revisión humana\.",
        lambda match: (
            "Riesgo de complejidad: observado; "
            + (
                "1 hallazgo de complejidad con fuente exacta sigue pendiente de revisión humana."
                if int(match.group(1)) == 1
                else f"{match.group(1)} hallazgos de complejidad con fuente exacta siguen pendientes de revisión humana."
            )
        ),
        text,
    )
    text = re.sub(
        r"(\d+) verified material finding\(s\) require disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'hallazgo material verificado requiere' if int(match.group(1)) == 1 else 'hallazgos materiales verificados requieren'} disposición."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) review-required candidate\(s\) remain unconfirmed\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'candidato que requiere revisión sigue' if int(match.group(1)) == 1 else 'candidatos que requieren revisión siguen'} sin confirmar."
        ),
        text,
    )
    text = re.sub(
        r"Historical evidence retains (\d+) non-success run\(s\); this remains a trend signal and is not treated as current-code failure\.",
        lambda match: (
            f"La evidencia histórica conserva {match.group(1)} "
            f"{'ejecución no exitosa' if int(match.group(1)) == 1 else 'ejecuciones no exitosas'}; "
            "esto sigue siendo una señal de tendencia y no se trata como un fallo del código actual."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) executable first-party code-risk finding\(s\) require exact-source disposition\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'hallazgo de riesgo en código ejecutable propio requiere' if int(match.group(1)) == 1 else 'hallazgos de riesgo en código ejecutable propio requieren'} disposición con fuente exacta."
        ),
        text,
    )
    text = re.sub(
        r"(\d+) unverified candidate\(s\) remain review-required; candidate volume affects assurance only and is not scored as confirmed defect volume\.",
        lambda match: (
            f"{match.group(1)} "
            f"{'candidato no verificado sigue requiriendo' if int(match.group(1)) == 1 else 'candidatos no verificados siguen requiriendo'} "
            "revisión; el volumen de candidatos solo afecta el aseguramiento y no se puntúa como volumen de defectos confirmados."
        ),
        text,
    )
    text = re.sub(
        r"(\d+)(?:\s+(.+?))? scanner candidate\(s\) were retained by count, but their raw payloads were unavailable to the canonical finding register\.",
        lambda match: (
            f"Se conservaron por conteo {match.group(1)} "
            f"{'candidato de analizador' if int(match.group(1)) == 1 else 'candidatos de analizadores'}, "
            + (
                "con disposición "
                + {
                    "verified material": "material verificado",
                    "review required": "requiere revisión",
                    "approved or nonblocking": "aprobada o no bloqueante",
                    "excluded test only": "excluida por ser solo de pruebas",
                }.get(match.group(2) or "", match.group(2) or "")
                + ", "
                if match.group(2)
                else ""
            )
            + "pero sus cargas sin procesar no estaban disponibles para el registro canónico de hallazgos."
        ),
        text,
    )
    text = re.sub(
        r"Jobs observed:\s*(\d+); success rate:\s*([^.]+)\.",
        r"Trabajos observados: \1; tasa de éxito: \2.",
        text,
    )
    text = re.sub(
        r"Deployments:\s*(\d+)/(\d+) successful\.",
        r"Despliegues: \1/\2 exitosos.",
        text,
    )
    text = re.sub(
        r"Merged pull requests:\s*(\d+); merge ratio:\s*([^.]+)\.",
        r"Solicitudes de incorporación fusionadas: \1; proporción de fusiones: \2.",
        text,
    )
    text = re.sub(
        r"Source analysis:\s*([^;]+); comments/strings excluded=([^.]+)\.",
        r"Análisis de código fuente: \1; comentarios/cadenas excluidos=\2.",
        text,
    )
    text = re.sub(
        r"Solicitudes de incorporación fusionadas:\s*(\d+); merge ratio:\s*([^.]+)\.",
        r"Solicitudes de incorporación fusionadas: \1; proporción de fusiones: \2.",
        text,
    )
    text = re.sub(
        r"Análisis de código fuente:\s*([^;]+); comments/strings excluded=([^.]+)\.",
        lambda match: (
            f"Análisis de código fuente: {match.group(1)}; comentarios/cadenas excluidos="
            f"{'sí' if match.group(2).casefold() == 'true' else 'no' if match.group(2).casefold() == 'false' else match.group(2)}."
        ),
        text,
    )
    text = re.sub(
        r"([A-Za-z0-9_.-]+): complete;",
        r"\1: completada;",
        text,
    )
    text = re.sub(
        r"(Coincidencia de SHA exacto de la configuración de flujos de trabajo|Permisos explícitos presentes):\s*(True|False)\.",
        lambda match: f"{match.group(1)}: {'Sí' if match.group(2) == 'True' else 'No'}.",
        text,
    )
    text = re.sub(r"(?<=:)\s*none(?=\.)", " ninguna", text, flags=re.IGNORECASE)

    def localized_subject(raw: str) -> str:
        subject = str(raw or "").strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", subject.casefold()).strip()
        if normalized in _STAGE_PHRASE_ES:
            return _STAGE_PHRASE_ES[normalized]
        translated = _CANONICAL_PARITY_EXACT.get(
            subject,
            _ES_EXTRA_EXACT.get(subject, ES_EXACT.get(subject)),
        )
        return str(translated or subject)

    text = re.sub(
        r"Decision-oriented summary for ([^.]+)\.",
        lambda match: f"Resumen orientado a decisiones para {localized_subject(match.group(1))}.",
        text,
    )
    text = re.sub(
        r"Exact immutable evidence item (\d+) for ([^.]+)\.",
        lambda match: f"Elemento {match.group(1)} de evidencia inmutable exacta para {localized_subject(match.group(2))}.",
        text,
    )
    text = re.sub(
        r"Review-limited finding for ([^.]+)\.",
        lambda match: f"Hallazgo limitado por revisión para {localized_subject(match.group(1))}.",
        text,
    )
    text = re.sub(
        r"One bounded evidence limitation for ([^.]+)\.",
        lambda match: f"Una limitación acotada de evidencia para {localized_subject(match.group(1))}.",
        text,
    )
    text = re.sub(
        r"Substantive summary for ([^.]+)\.",
        lambda match: f"Resumen sustantivo de {localized_subject(match.group(1))}.",
        text,
    )
    text = re.sub(
        r"Retained finding for ([A-Za-z0-9_.-]+)\.",
        lambda match: f"Hallazgo conservado para {localized_subject(match.group(1))}.",
        text,
    )
    text = re.sub(
        r"Human context limitation for ([A-Za-z0-9_.-]+)\.",
        lambda match: f"Limitación de contexto humano para {localized_subject(match.group(1))}.",
        text,
    )
    text = text.replace("exact commit=yes", "commit exacto=sí")
    text = text.replace("exact commit=no", "commit exacto=no")
    text = text.replace("artifact=retained", "artefacto=conservado")
    text = text.replace("artifact=missing", "artefacto=faltante")
    text = text.replace("retained finding count=", "conteo de hallazgos conservados=")
    text = re.sub(
        r"\s*·\s*Incomplete applicable analyzers:\s*(\d+)",
        "",
        text,
    )
    return text


def _localize_tree(
    value: Any,
    key: str = "",
    path: tuple[str, ...] = (),
    *,
    engagement_literals: tuple[str, ...] = (),
    preserve_engagement_literals: bool = False,
    preserve_client_literal_lines: bool = False,
) -> Any:
    if any(segment in _RAW_CANONICAL_SUBTREES for segment in path):
        return deepcopy(value)
    if key in _PROTECTED_FIELDS:
        return deepcopy(value)
    if isinstance(value, Mapping):
        client_evidence_summary = (
            str(value.get("stage_id") or "").strip() == "client_evidence_summary"
        )
        client_human_evidence = str(value.get("stage_id") or "").strip().startswith(
            "client_human_evidence_"
        )
        return {
            str(name): _localize_tree(
                item,
                str(name),
                (*path, str(name)),
                engagement_literals=engagement_literals,
                preserve_engagement_literals=(
                    preserve_engagement_literals
                    or (
                        client_evidence_summary
                        and str(name) in {"evidence", "unavailable"}
                    )
                ),
                preserve_client_literal_lines=(
                    preserve_client_literal_lines
                    or (client_human_evidence and str(name) == "evidence")
                ),
            )
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [
            _localize_tree(
                item,
                key,
                path,
                engagement_literals=engagement_literals,
                preserve_engagement_literals=preserve_engagement_literals,
                preserve_client_literal_lines=preserve_client_literal_lines,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _localize_tree(
                item,
                key,
                path,
                engagement_literals=engagement_literals,
                preserve_engagement_literals=preserve_engagement_literals,
                preserve_client_literal_lines=preserve_client_literal_lines,
            )
            for item in value
        )
    if isinstance(value, str):
        if preserve_client_literal_lines:
            from nico.comprehensive_human_evidence_report_v1 import (
                _translate_client_literal_line,
            )

            return _translate_client_literal_line(value)
        if preserve_engagement_literals and engagement_literals:
            placeholders: dict[str, str] = {}
            protected = value
            for literal in engagement_literals:
                if literal not in protected:
                    continue
                token = f"\ue100{len(placeholders)}\ue101"
                while token in protected:
                    token += "\ue102"
                protected = protected.replace(literal, token)
                placeholders[token] = literal
            translated = _translate_presentation_field(protected, key)
            for token, literal in placeholders.items():
                translated = translated.replace(token, literal)
            return translated
        return _translate_presentation_field(value, key)
    return deepcopy(value)


def _render_inputs(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    stages = [
        item
        for item in canonical.get("stage_summaries") or []
        if isinstance(item, Mapping)
    ]
    generated_at = str(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
        or ""
    )
    engagement_literals = tuple(
        sorted(
            {
                str(identity.get(field))
                for field in (
                    "customer_name",
                    "project_name",
                    "primary_technical_contact",
                    "access_method",
                    "authorized_scope",
                )
                if isinstance(identity.get(field), str) and identity.get(field)
            },
            key=lambda item: (-len(item), item),
        )
    )
    return (
        _localize_tree(identity, path=("identity",)),
        _localize_tree(
            assessment,
            path=("assessment",),
            engagement_literals=engagement_literals,
        ),
        _localize_tree(
            stages,
            path=("stage_summaries",),
            engagement_literals=engagement_literals,
        ),
        generated_at,
    )


def _post_render_protected_literals(value: Any, key: str = "") -> tuple[str, ...]:
    literals: set[str] = set()

    def collect(item: Any, field: str = "") -> None:
        if isinstance(item, Mapping):
            for name, child in item.items():
                collect(child, str(name))
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                collect(child, field)
            return
        if field in _POST_RENDER_PROTECTED_FIELDS and isinstance(item, str):
            literal = str(item)
            if literal:
                literals.add(literal)

    collect(value, key)
    return tuple(sorted(literals, key=lambda item: (-len(item), item)))


def _translate_preserving_literals(
    value: str,
    protected_literals: tuple[str, ...],
) -> str:
    text = str(value or "")
    placeholders: dict[str, str] = {}
    for literal in protected_literals:
        if literal not in text:
            continue
        token = f"\ue000{len(placeholders)}\ue001"
        text = text.replace(literal, token)
        placeholders[token] = literal
    text = _translate_presentation(text)
    for token, literal in placeholders.items():
        text = text.replace(token, literal)
    return text


def _localize_markdown(
    markdown: str,
    protected_literals: tuple[str, ...] = (),
) -> str:
    parts = _LITERAL_MARKDOWN_RE.split(str(markdown or ""))
    localized: list[str] = []
    for part in parts:
        stripped = part.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            localized.append(part)
            continue
        placeholders: dict[str, str] = {}

        def protect(match: re.Match[str]) -> str:
            token = f"\x00NICO_LITERAL_{len(placeholders)}\x00"
            placeholders[token] = match.group(0)
            return token

        protected = _INLINE_LITERAL_RE.sub(protect, part)
        protected = _translate_preserving_literals(protected, protected_literals)
        for token, literal in placeholders.items():
            protected = protected.replace(token, literal)
        localized.append(protected)
    return "".join(localized)


def render_spanish_markdown(canonical: Mapping[str, Any]) -> str:
    """Render es-MX from the exact English canonical section contract."""

    identity, assessment, stages, generated_at = _render_inputs(canonical)
    return _markdown(
        identity,
        assessment,
        stages,
        generated_at,
        localize_presentation=_translate_presentation,
    )


def render_spanish_html(markdown: str, title: str) -> str:
    """Use the English semantic HTML shell with es-MX document chrome."""

    rendered = _semantic_html(str(markdown or ""), str(title or ""))
    return (
        rendered.replace('<html lang="en">', '<html lang="es-MX">', 1)
        .replace(
            "DRAFT · HUMAN REVIEW REQUIRED",
            "BORRADOR AUTOMATIZADO · REVISIÓN HUMANA REQUERIDA",
            1,
        )
        .replace(
            "<p>&lt;!-- CLIENT DELIVERY NOT AUTHORIZED --&gt;</p>",
            "<!-- CLIENT DELIVERY NOT AUTHORIZED -->",
        )
    )


def _localize_pdf_operand(
    value: str,
    protected_literals: tuple[str, ...] = (),
) -> str:
    raw = str(value or "")
    local_page = _LOCAL_PAGE_LABEL.fullmatch(raw.strip())
    if local_page:
        return re.sub(r"Page", "Página", raw, count=1, flags=re.IGNORECASE)
    return _translate_preserving_literals(raw, protected_literals)


def render_spanish_pdf(canonical: Mapping[str, Any]) -> tuple[bytes, int]:
    """Render the English canonical PDF topology with es-MX presentation copy."""

    identity, assessment, stages, generated_at = _render_inputs(canonical)
    encoded, error, page_count = _pdf(
        identity,
        assessment,
        stages,
        generated_at,
        localize_presentation=_translate_presentation,
    )
    if error or not encoded:
        raise ValueError(f"canonical Spanish PDF renderer failed: {error or 'empty PDF'}")
    pdf = base64.b64decode(encoded)
    if not pdf.startswith(b"%PDF"):
        raise ValueError("canonical Spanish PDF renderer returned an invalid PDF")

    localized_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if localized_count != page_count:
        raise ValueError("canonical Spanish PDF localization changed page topology")
    return pdf, localized_count


__all__ = [
    "VERSION",
    "render_spanish_html",
    "render_spanish_markdown",
    "render_spanish_pdf",
]
