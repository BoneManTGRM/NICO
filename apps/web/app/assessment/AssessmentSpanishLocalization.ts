const EXACT_SPANISH = new Map<string, string>([
  ["code audit", "Auditoría de código"],
  ["dependency / library ecosystem", "Dependencias y ecosistema de bibliotecas"],
  ["dependency and supply-chain decision record", "Registro de decisión de dependencias y cadena de suministro"],
  ["secrets exposure review", "Revisión de exposición de secretos"],
  ["secrets exposure decision record", "Registro de decisión sobre exposición de secretos"],
  ["static analysis", "Análisis estático"],
  ["static analysis decision record", "Registro de decisión de análisis estático"],
  ["ci/cd analysis", "Análisis de CI/CD"],
  ["ci/cd and release decision record", "Registro de decisión de CI/CD y publicación"],
  ["architecture & technical debt", "Arquitectura y deuda técnica"],
  ["architecture decision record", "Registro de decisión de arquitectura"],
  ["velocity / complexity", "Velocidad y complejidad"],
  ["velocity, complexity, and ownership decision record", "Registro de decisión de velocidad, complejidad y propiedad"],
  ["scanner worker evidence", "Evidencia de los analizadores"],
  ["client / human acceptance", "Aceptación del cliente y revisión humana"],
  ["technical score and assurance", "Puntuación técnica y garantía de evidencia"],
  ["technical score and evidence assurance", "Puntuación técnica y garantía de evidencia"],
  ["score contribution and assurance constraints", "Contribución de la puntuación y restricciones de evidencia"],
  ["request accepted", "Solicitud aceptada"],
  ["repository evidence", "Evidencia del repositorio"],
  ["scanner suite", "Conjunto de analizadores"],
  ["scanner reconciliation", "Conciliación de analizadores"],
  ["evidence attachment", "Adjunto de evidencia"],
  ["accuracy review", "Revisión de exactitud"],
  ["technical scoring", "Puntuación técnica"],
  ["score reconciliation", "Conciliación de puntuación"],
  ["report generation", "Generación del informe"],
  ["truth and review gates", "Controles de veracidad y revisión"],
  ["authorization and scope", "Autorización y alcance"],
  ["immutable repository snapshot", "Instantánea inmutable del repositorio"],
  ["repository and delivery evidence", "Evidencia del repositorio y de entrega"],
  ["dependency, security, and static analysis", "Dependencias, seguridad y análisis estático"],
  ["ci/cd, architecture, complexity, and velocity", "CI/CD, arquitectura, complejidad y velocidad"],
  ["evidence reconciliation and scoring", "Conciliación de evidencia y puntuación"],
  ["core decision report", "Informe principal de decisiones"],
  ["deep scanner triage", "Triaje profundo de analizadores"],
  ["functional qa", "QA funcional"],
  ["platform parity", "Paridad de plataformas"],
  ["deployment and infrastructure", "Despliegue e infraestructura"],
  ["architecture and data flow", "Arquitectura y flujo de datos"],
  ["developer delivery process", "Proceso de entrega del equipo"],
  ["stakeholder and business alignment", "Alineación con negocio y partes interesadas"],
  ["requirements traceability", "Trazabilidad de requisitos"],
  ["historical trends and change failure", "Tendencias históricas y fallos de cambio"],
  ["six-month roadmap", "Hoja de ruta de seis meses"],
  ["staffing, sequencing, and cost", "Personal, secuencia y costo"],
  ["risk reduction and executive briefing", "Reducción de riesgo e informe ejecutivo"],
  ["final comprehensive report", "Informe Integral final"],
  ["cross-format truth verification", "Verificación de veracidad entre formatos"],
  ["human-review request", "Solicitud de revisión humana"],
  ["client acceptance pending", "Aceptación del cliente pendiente"],
  ["complete", "Completo"],
  ["completed", "Completado"],
  ["running", "En ejecución"],
  ["running automatically", "Ejecutándose automáticamente"],
  ["queued", "En cola"],
  ["pending", "Pendiente"],
  ["planned", "Planificado"],
  ["ready", "Listo"],
  ["starting", "Iniciando"],
  ["skipped", "Omitido"],
  ["attached", "Adjunto"],
  ["verified", "Verificado"],
  ["review limited", "Revisión limitada"],
  ["review_limited", "Revisión limitada"],
  ["review_limited_not_scored", "Revisión limitada · sin puntuación"],
  ["blocked", "Bloqueado"],
  ["failed", "Fallido"],
  ["unavailable", "No disponible"],
  ["timed out", "Tiempo agotado"],
  ["timed_out", "Tiempo agotado"],
  ["interrupted", "Interrumpido"],
  ["rejected", "Rechazado"],
  ["supplemental", "Complementario"],
  ["human review pending", "Revisión humana pendiente"],
  ["human review required", "Revisión humana obligatoria"],
  ["final report", "Informe final"],
  ["pending approval", "Aprobación pendiente"],
  ["pending human approval", "Aprobación humana pendiente"],
  ["not scored", "Sin puntuación"],
  ["not verified", "No verificado"],
  ["unverified", "No verificado"],
  ["exceptional", "Excepcional"],
  ["strong", "Fuerte"],
  ["moderate", "Moderado"],
  ["mid", "Moderado"],
  ["weak", "Débil"],
  ["critical", "Crítico"],
  ["green", "Verificado"],
  ["yellow", "Revisión limitada"],
  ["red", "Bloqueado"],
  ["gray", "Pendiente"],
  ["high", "Alta"],
  ["medium", "Media"],
  ["low", "Baja"],
  ["unknown", "Desconocido"],
  ["scored", "Puntuado"],
  ["supplemental / review control", "Control complementario o sujeto a revisión"],
  ["canonical scored control", "Control puntuado canónico"],
  ["no retained item.", "No se conservó ningún elemento."],
  ["no section summary retained.", "No se conservó un resumen de la sección."],
  ["no material score constraint retained.", "No se conservó ninguna restricción material de puntuación."],
  ["exact evidence", "Evidencia exacta"],
  ["open findings", "Hallazgos abiertos"],
  ["limitations", "Limitaciones"],
  ["score and assurance rationale", "Justificación de puntuación y evidencia"],
  ["technical score", "Puntuación técnica"],
  ["technical band", "Nivel técnico"],
  ["evidence assurance", "Garantía de evidencia"],
  ["assurance", "Evidencia"],
  ["canonical status", "Estado canónico"],
  ["confidence", "Confianza"],
  ["treatment", "Tratamiento"],
  ["control", "Control"],
  ["primary constraint", "Restricción principal"],
  ["score-derived contribution", "Contribución derivada de la puntuación"],
]);

const JSON_KEY_SPANISH = new Map<string, string>([
  ["status", "estado"],
  ["message", "mensaje"],
  ["summary", "resumen"],
  ["evidence", "evidencia"],
  ["findings", "hallazgos"],
  ["unavailable", "no_disponible"],
  ["repository", "repositorio"],
  ["repository_url", "url_del_repositorio"],
  ["commit_sha", "sha_del_commit"],
  ["snapshot_commit_sha", "sha_de_la_instantánea"],
  ["scanner_status", "estado_de_analizadores"],
  ["progress_percent", "porcentaje_de_progreso"],
  ["analyzed_files", "archivos_analizados"],
  ["source_files", "archivos_fuente"],
  ["source_loc", "líneas_de_código_fuente"],
  ["function_units", "unidades_de_función"],
  ["risk", "riesgo"],
  ["score", "puntuación"],
  ["technical_score", "puntuación_técnica"],
  ["evidence_adjusted_score", "puntuación_ajustada_por_evidencia"],
  ["candidate_count", "cantidad_de_candidatos"],
  ["blocking", "bloqueantes"],
  ["needs_review", "requieren_revisión"],
  ["approved", "aprobados"],
  ["candidate_false_positive", "posibles_falsos_positivos"],
  ["duration_seconds", "duración_en_segundos"],
  ["started_at", "iniciado_en"],
  ["completed_at", "completado_en"],
  ["adapter", "adaptador"],
  ["durable", "durable"],
  ["recorded", "registrado"],
]);

const SPANISH_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bExpress completed its evidence, scoring, reporting, and truth-gate stages\. Human review remains required before delivery\./gi, "Express completó las etapas de evidencia, puntuación, informe y controles de veracidad. La revisión humana sigue siendo obligatoria antes de la entrega."],
  [/\bComprehensive completed every automated stage and stopped at the required human-review gate\./gi, "Integral completó todas las etapas automatizadas y se detuvo ante la revisión humana obligatoria."],
  [/\bThe final report is complete\. The team must review the exact evidence-bound package and approve it before client delivery; no separate report rewrite is required\./gi, "El informe final está completo. El equipo debe revisar el paquete exacto vinculado a evidencia y aprobarlo antes de entregarlo al cliente; no es necesario rehacer el informe."],
  [/\bAutomated truth and review gates completed\. Human review remains required before delivery\./gi, "Los controles automatizados de veracidad y revisión terminaron. La revisión humana sigue siendo obligatoria antes de la entrega."],
  [/\bThe assessment stopped because a required stage failed or was blocked\./gi, "La evaluación se detuvo porque una etapa obligatoria falló o quedó bloqueada."],
  [/\bTechnical health and evidence assurance are independent dimensions\./gi, "La salud técnica y la garantía de evidencia son dimensiones independientes."],
  [/\bA high technical score can remain review-limited when an analyzer failed, timed out, returned unresolved candidates, or material evidence is unavailable\./gi, "Una puntuación técnica alta puede permanecer sujeta a revisión cuando un analizador falla, agota el tiempo, devuelve candidatos sin resolver o falta evidencia material."],
  [/\bDelivery approval remains a separate human decision\./gi, "La aprobación de entrega sigue siendo una decisión humana independiente."],
  [/\bAssurance remains separate from the technical percentage\. Human review and client-delivery controls are not changed by the technical band\./gi, "La garantía de evidencia permanece separada del porcentaje técnico. El nivel técnico no modifica los controles de revisión humana ni de entrega al cliente."],
  [/\bStatic analysis reports each analyzer independently; unresolved failures, timeouts, unavailable analyzers, and candidate findings remain explicitly separated from completed evidence\./gi, "El análisis estático informa cada analizador por separado; los fallos sin resolver, tiempos agotados, analizadores no disponibles y hallazgos candidatos permanecen separados explícitamente de la evidencia completada."],
  [/\bSecrets review reports scanner candidates, failures, and timeouts as review-limited evidence; it does not establish credential exposure until exact locations and values are triaged\./gi, "La revisión de secretos presenta candidatos, fallos y tiempos agotados como evidencia sujeta a revisión; no confirma exposición de credenciales hasta que se revisen las ubicaciones y valores exactos."],
  [/\bArchitecture review includes worker-backed call-graph, cyclomatic complexity, hotspot, churn, ownership, dependency-risk, and source-footprint evidence\./gi, "La revisión de arquitectura incluye evidencia del grafo de llamadas, complejidad ciclomática, puntos críticos, rotación de cambios, propiedad, riesgo de dependencias y huella del código fuente."],
  [/\bWork-vs-expected signal uses velocity, PR traceability, source footprint, available supporting evidence, disclosed findings, and explicit missing runtime artifacts; it does not claim final release-readiness\./gi, "La señal de trabajo frente a lo esperado utiliza velocidad, trazabilidad de solicitudes de cambio, huella del código fuente, evidencia de respaldo disponible, hallazgos declarados y artefactos de ejecución faltantes; no afirma preparación final para publicación."],
  [/\bThe scanner suite executed against the exact commit captured for this Express run\. Its output is attached as supplemental diagnostic evidence and mapped into the relevant core evidence sections without silently inflating the overall maturity score\./gi, "El conjunto de analizadores se ejecutó contra el commit exacto capturado para esta ejecución Express. Su salida se adjunta como evidencia diagnóstica complementaria y se asigna a las secciones principales correspondientes sin aumentar de forma silenciosa la puntuación general de madurez."],
  [/\bFinal report acceptance is not scored until an approved same-project review record exists\./gi, "La aceptación final del informe no se puntúa hasta que exista un registro de revisión aprobado para el mismo proyecto."],
  [/\bSource-file footprint is large and increases review scope; repository size is not scored as technical debt by itself\./gi, "La huella de archivos fuente es grande y amplía el alcance de revisión; el tamaño del repositorio no se puntúa por sí solo como deuda técnica."],
  [/\bTotal source LOC is high for an Express review and increases review depth; size alone does not reduce maintainability score\./gi, "El total de líneas de código fuente es alto para una revisión Express y aumenta la profundidad del análisis; el tamaño por sí solo no reduce la puntuación de mantenibilidad."],
  [/\bAt least one function has very high cyclomatic complexity and should be decomposed or tested heavily\./gi, "Al menos una función tiene una complejidad ciclomática muy alta y debe descomponerse o someterse a pruebas exhaustivas."],
  [/\bFunction-level complexity risk is concentrated in ([0-9]+) source file\(s\)\./gi, "El riesgo de complejidad a nivel de función se concentra en $1 archivo(s) fuente."],
  [/\bComplexity and high churn overlap in ([0-9]+) delivery hotspot file\(s\)\./gi, "La complejidad y la alta rotación de cambios coinciden en $1 archivo(s) crítico(s) de entrega."],
  [/\bLarge-file and complexity risk overlap in ([0-9]+) source file\(s\)\./gi, "El riesgo por archivos grandes y complejidad coincide en $1 archivo(s) fuente."],
  [/\bOwnership concentration is elevated across the source footprint\./gi, "La concentración de propiedad es elevada en la huella del código fuente."],
  [/\bComplexity hotspot:/gi, "Punto crítico de complejidad:"],
  [/\bTop complexity hotspot:/gi, "Principal punto crítico de complejidad:"],
  [/\bComplexity engine analyzed ([0-9]+) source file\(s\), ([0-9]+) source LOC, and ([0-9]+) function-like units\./gi, "El motor de complejidad analizó $1 archivo(s) fuente, $2 líneas de código fuente y $3 unidades similares a funciones."],
  [/\bEstimated call graph edges: ([0-9]+); max file cyclomatic complexity: ([0-9]+)\./gi, "Aristas estimadas del grafo de llamadas: $1; complejidad ciclomática máxima por archivo: $2."],
  [/\bHotspot candidates identified: ([0-9]+); manifest dependency count: ([0-9]+)\./gi, "Candidatos a puntos críticos identificados: $1; dependencias declaradas en manifiestos: $2."],
  [/\bGit churn data available for ([0-9]+) file\(s\)\./gi, "Hay datos de rotación de cambios de Git para $1 archivo(s)."],
  [/\bOwnership signal available for ([0-9]+) file\(s\)\./gi, "Hay señal de propiedad para $1 archivo(s)."],
  [/\bComplexity engine risk level: ([a-z_-]+); complexity score=([0-9]+)\/100; model=([a-z_-]+)\./gi, "Nivel de riesgo del motor de complejidad: $1; puntuación de complejidad=$2/100; modelo=$3."],
  [/\bArchitecture complexity support: current-run complexity artifact reports/gi, "Respaldo de complejidad de arquitectura: el artefacto de complejidad de la ejecución actual informa"],
  [/\bComplexity evidence verified for this report run:/gi, "Evidencia de complejidad verificada para esta ejecución del informe:"],
  [/\bCommit velocity: ([0-9]+) commits over ([0-9]+) days \(([0-9.]+)\/week\)\./gi, "Velocidad de commits: $1 commits durante $2 días ($3 por semana)."],
  [/\bPull request traceability ratio:/gi, "Proporción de trazabilidad de solicitudes de cambio:"],
  [/\bScanner-worker static tools reported ([0-9]+) finding\(s\)\./gi, "Los analizadores estáticos informaron $1 hallazgo(s) candidato(s)."],
  [/\bbandit ended with status failed; its output requires human review before client-facing conclusions\./gi, "Bandit terminó con estado fallido; su salida requiere revisión humana antes de emitir conclusiones para el cliente."],
  [/\bsemgrep returned ([0-9]+) finding\(s\) requiring human triage\./gi, "Semgrep devolvió $1 hallazgo(s) candidato(s) que requieren triaje humano."],
  [/\btypescript returned ([0-9]+) finding\(s\) requiring human triage\./gi, "TypeScript devolvió $1 hallazgo(s) candidato(s) que requieren triaje humano."],
  [/\bParsed Bandit artifact reported ([0-9]+) finding\(s\)\./gi, "El artefacto analizado de Bandit informó $1 hallazgo(s) candidato(s)."],
  [/\bBandit triage summary:/gi, "Resumen de triaje de Bandit:"],
  [/\bAccepted clean execution evidence unavailable for:/gi, "No hay evidencia aceptada de ejecución limpia para:"],
  [/\bwas unavailable in the exact-snapshot scanner:/gi, "no estuvo disponible en el analizador de la instantánea exacta:"],
  [/\bNo ESLint configuration exists and the package lint script does not execute ESLint; TypeScript compilation must not be relabeled as ESLint evidence\./gi, "No existe una configuración de ESLint y el script de lint del paquete no ejecuta ESLint; la compilación de TypeScript no debe presentarse como evidencia de ESLint."],
  [/\bBandit source distinction:/gi, "Distinción de la fuente de Bandit:"],
  [/\bScanner-worker static artifacts were observed for:/gi, "Se observaron artefactos de analizadores estáticos para:"],
  [/\bExecution acceptance is determined per analyzer from its canonical exit disposition\./gi, "La aceptación de ejecución se determina por analizador según su disposición de salida canónica."],
  [/\bBandit triage artifact attached:/gi, "Artefacto de triaje de Bandit adjunto:"],
  [/\bBandit evidence source distinction:/gi, "Distinción de la fuente de evidencia de Bandit:"],
  [/\bparsed prior\/sample or attached artifact findings are separate from live scanner-worker Bandit execution for this report run\./gi, "los hallazgos analizados de una muestra previa o de un artefacto adjunto son independientes de la ejecución en vivo de Bandit para esta ejecución del informe."],
  [/\bCanonical scanner disposition:/gi, "Disposición canónica del analizador:"],
  [/\bthe missing analyzer is disclosed and not substituted by another tool\./gi, "el analizador ausente se declara y no se sustituye por otra herramienta."],
  [/\bhuman triage required\./gi, "se requiere triaje humano."],
  [/\bTruth reconciliation:/gi, "Conciliación de veracidad:"],
  [/\baccepted clean execution evidence is not established for/gi, "no se ha establecido evidencia aceptada de ejecución limpia para"],
  [/\battached or parsed artifacts remain diagnostic until the canonical analyzer disposition is completed, explicitly inapplicable, or human-approved as review-limited\./gi, "los artefactos adjuntos o analizados siguen siendo diagnósticos hasta que la disposición canónica del analizador se complete, se declare explícitamente no aplicable o se apruebe mediante revisión humana como evidencia limitada."],
  [/\bExact-snapshot ([A-Za-z0-9_-]+) status=completed; findings=([0-9]+)/gi, "Instantánea exacta: $1, estado=completado; hallazgos=$2"],
  [/\bstatus=completed_clean/gi, "estado=completado_sin_hallazgos"],
  [/\bstatus=completed_with_candidates/gi, "estado=completado_con_candidatos"],
  [/\bstatus=completed/gi, "estado=completado"],
  [/\bstatus=failed/gi, "estado=fallido"],
  [/\bstatus=unavailable/gi, "estado=no_disponible"],
  [/\bfindings=/gi, "hallazgos="],
  [/\bcandidates=/gi, "candidatos="],
  [/\bblocking=/gi, "bloqueantes="],
  [/\bneeds_review=/gi, "requieren_revisión="],
  [/\bapproved=/gi, "aprobados="],
  [/\bcandidate_false_positive=/gi, "posibles_falsos_positivos="],
  [/\bverified blockers=/gi, "bloqueantes verificados="],
  [/\breview required/gi, "revisión obligatoria"],
  [/\brequires human review/gi, "requiere revisión humana"],
  [/\brequiring human review/gi, "que requieren revisión humana"],
  [/\brequiring human triage/gi, "que requieren triaje humano"],
  [/\bunverified candidate\(s\)/gi, "candidato(s) sin verificar"],
  [/\bcandidate false-positive\(s\)/gi, "posible(s) falso(s) positivo(s)"],
  [/\bsource file\(s\)/gi, "archivo(s) fuente"],
  [/\bsource LOC/gi, "líneas de código fuente"],
  [/\bfunction-like units/gi, "unidades similares a funciones"],
  [/\bcall graph edges/gi, "aristas del grafo de llamadas"],
  [/\btechnical debt/gi, "deuda técnica"],
  [/\btechnical health/gi, "salud técnica"],
  [/\bevidence assurance/gi, "garantía de evidencia"],
  [/\bhuman review/gi, "revisión humana"],
  [/\bclient delivery/gi, "entrega al cliente"],
  [/\bcurrent run/gi, "ejecución actual"],
  [/\bcurrent-run/gi, "ejecución actual"],
  [/\bexact snapshot/gi, "instantánea exacta"],
  [/\bexact-snapshot/gi, "instantánea exacta"],
  [/\bsource footprint/gi, "huella del código fuente"],
  [/\bmanifest dependency count/gi, "cantidad de dependencias en manifiestos"],
  [/\bownership signal/gi, "señal de propiedad"],
  [/\bcomplexity score/gi, "puntuación de complejidad"],
  [/\brisk level/gi, "nivel de riesgo"],
  [/\breport run/gi, "ejecución del informe"],
  [/\bmodel=legacy/gi, "modelo=heredado"],
];

function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function localizeSpanishText(value: string | null | undefined): string {
  const source = String(value || "");
  if (!source.trim()) return source;
  const leading = source.match(/^\s*/)?.[0] || "";
  const trailing = source.match(/\s*$/)?.[0] || "";
  const core = compact(source);
  const exact = EXACT_SPANISH.get(core.toLowerCase());
  let localized = exact || core;
  for (const [pattern, replacement] of SPANISH_REPLACEMENTS) {
    localized = localized.replace(pattern, replacement);
  }
  return `${leading}${localized}${trailing}`;
}

function localizeSpanishJson(value: unknown): unknown {
  if (typeof value === "string") return localizeSpanishText(value);
  if (Array.isArray(value)) return value.map(localizeSpanishJson);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      JSON_KEY_SPANISH.get(key) || key,
      localizeSpanishJson(item),
    ]),
  );
}

function localizeJsonBlocks(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>("pre.json-block").forEach((node) => {
    const source = node.textContent || "";
    try {
      const parsed = JSON.parse(source) as unknown;
      const localized = JSON.stringify(localizeSpanishJson(parsed), null, 2);
      if (localized !== source) node.textContent = localized;
    } catch {
      const localized = localizeSpanishText(source);
      if (localized !== source) node.textContent = localized;
    }
  });
}

export function localizeSpanishAssessmentDom(root: Document | HTMLElement = document): void {
  if (!document.documentElement.lang.toLowerCase().startsWith("es")) return;
  localizeJsonBlocks(root);
  const container: Node = root instanceof Document ? root.body : root;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let current = walker.nextNode();
  while (current) {
    if (current instanceof Text) nodes.push(current);
    current = walker.nextNode();
  }
  nodes.forEach((node) => {
    const parent = node.parentElement;
    if (!parent || parent.closest("script, style, code, pre, textarea, [data-no-localize='true']")) return;
    const source = node.nodeValue || "";
    const localized = localizeSpanishText(source);
    if (localized !== source) node.nodeValue = localized;
  });
}
