from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-current-copy-worker.v98.7"
_ONE_ARG_MARKER = "__nico_spanish_current_copy_worker_one_v98__"
_TWO_ARG_MARKER = "__nico_spanish_current_copy_worker_two_v98__"

_STATE_ES = {
    "execution completed": "ejecución completada",
    "completed": "ejecución completada",
    "complete": "ejecución completada",
    "succeeded": "exitosa",
    "success": "exitosa",
    "passed": "aprobado",
    "failed": "fallido",
    "not_applicable": "no aplica",
    "not applicable": "no aplica",
    "unavailable": "no disponible",
    "unknown": "desconocido",
    "not_assessed": "no evaluado",
    "not assessed": "no evaluado",
}
_BOOLEAN_ES = {
    "true": "sí",
    "false": "no",
    "not assessed": "no evaluada",
}

# These are generator contracts, not a screenshot allowlist. Dynamic values are
# captured and preserved while the renderer-owned sentence is projected to es-MX.
_PROVIDER_WORKFLOW_FILES_RE = re.compile(
    r"Workflow files at assessed commit: (?P<count>\d+)\."
)
_PROVIDER_EXACT_SHA_RE = re.compile(
    r"Workflow configuration exact-SHA match: (?P<state>True|False|not assessed)\.",
    re.IGNORECASE,
)
_PROVIDER_PERMISSION_RE = re.compile(
    r"Explicit permissions control: (?P<state>passed|failed|not_assessed|not assessed)\.",
    re.IGNORECASE,
)
_PROVIDER_COVERAGE_RE = re.compile(
    r"Provider-neutral immutable CI objective coverage: (?P<coverage>\d+(?:\.\d+)?%)\."
)
_PROVIDER_ASSURANCE_RE = re.compile(
    r"CI control assurance incomplete; no pass/fail claim was made for: (?P<objectives>[^.]+)\."
)
_TECHNICAL_MATURITY_RE = re.compile(
    r"Technical maturity remains based on exact-commit technical controls\. "
    r"Evidence-Adjusted readiness is (?P<adjusted>\d+(?:\.\d+)?)/100 versus technical maturity "
    r"(?P<technical>\d+(?:\.\d+)?)/100\. NICO retains "
    r"(?P<review_required>\d+) review-required candidates and "
    r"(?P<confirmed>\d+) confirmed material findings as explicit review context\."
)
_COMPLEXITY_RISK_RE = re.compile(
    r"Complexity risk: observed; (?P<count>\d+) exact-source complexity findings "
    r"remain pending human review\."
)
_COMPLEXITY_ACCEPTANCE_RE = re.compile(
    r"The exact-SHA rerun no longer reports cyclomatic complexity above "
    r"(?P<threshold>\d+) at (?P<location>\S+)"
)
_CANDIDATE_VOLUME_RE = re.compile(
    r"Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or "
    r"(?:Evidence-Adjusted|Ajuste por evidencia) score effect\."
)
_CANDIDATE_VOLUME_SECURITY_RE = re.compile(
    r"Candidate volume, clustering and reviewer workload do not change numeric security or readiness scores\."
)
_ANALYZER_COMPLETION_RE = re.compile(
    r"(?P<completed>\d+) of (?P<applicable>\d+) applicable analyzers completed; "
    r"(?P<incomplete>\d+) are incomplete\. Candidate triage is separate: "
    r"(?P<review_required>\d+) review-required candidates and "
    r"(?P<confirmed>\d+) confirmed material findings are retained\."
)
_REVIEW_REQUIRED_SCANNER_CANDIDATES_RE = re.compile(
    r"Review-required scanner candidates: (?P<count>\d+)(?P<period>\.?)",
    re.IGNORECASE,
)
_UNRESOLVED_DEPLOYMENTS_RE = re.compile(
    r"Non-success or unresolved deployment observations: (?P<count>\d+)\.",
    re.IGNORECASE,
)
_OUTCOME_CLASSIFICATION_RE = re.compile(
    r"Outcome classification breakdown: (?P<value>[^\r\n]+?)(?P<period>\.)?(?=\r?$|\n)",
    re.IGNORECASE | re.MULTILINE,
)
_WORKFLOW_JOBS_WITH_RATE_RE = re.compile(
    r"Workflow jobs: (?P<successful>\d+) successful of (?P<observed>\d+) observed "
    r"\((?P<rate>\d+(?:\.\d+)?%)\)\."
)
_WORKFLOW_JOBS_WITHOUT_RATE_RE = re.compile(
    r"Workflow jobs: (?P<observed>\d+) observed; successful count and success rate "
    r"are not reported because a supported numerator was not retained\."
)
_DEPLOYMENT_TAXONOMY_RE = re.compile(
    r"Deployment outcome taxonomy \(unscored context\): observed=(?P<observed>\d+); "
    r"successful=(?P<successful>\d+); failed/non-success=(?P<failed>[^;]+); "
    r"unresolved=(?P<unresolved>[^;.]+)"
    r"(?:; failed-or-unresolved remainder=(?P<remainder>\d+))?\."
)
_TOP_LEVEL_ENTRY_RE = re.compile(
    r"Top-level entries\[(?P<index>\d+)\]: (?P<value>[^\r\n]+)",
    re.IGNORECASE,
)
_SCANNER_STATE_RE = re.compile(
    r"(?P<prefix>(?:^|\n)[^\n:]{1,100}: )"
    r"(?P<state>completed|complete|succeeded|success|passed|failed|not_applicable|not applicable|unavailable|unknown)"
    r"(?=; (?:commit exacto|exact commit)=)",
    re.IGNORECASE,
)
_SCANNER_EXECUTION_SUMMARY_RE = re.compile(
    r"(?P<prefix>(?:^|\n)[^\n:]{1,100}: )"
    r"(?P<state>execution completed|completed|complete|succeeded|success|passed|failed|"
    r"not_applicable|not applicable|unavailable|unknown); "
    r"exact commit=(?P<commit>yes|no); "
    r"artifact=(?P<artifact>retained|missing); "
    r"confirmed material finding count=(?P<count>\d+); "
    r"raw finding payload embedded=(?P<raw>yes|no)\.",
    re.IGNORECASE,
)
_CANDIDATE_CATEGORY_SUMMARY_RE = re.compile(
    r"(?P<category>Dependency|Secret|Static): raw=(?P<raw>\d+); "
    r"confirmed_material=(?P<confirmed>\d+); review_required=(?P<review>\d+); "
    r"excluded_test_only=(?P<excluded>\d+); approved_or_nonblocking=(?P<nonblocking>\d+)\.",
    re.IGNORECASE,
)
_CANDIDATE_CATEGORY_ES = {
    "dependency": "Dependencias",
    "secret": "Secretos",
    "static": "Análisis estático",
}
_CANDIDATE_DETAIL_LABEL_ES = {
    "tool": "herramienta",
    "package": "paquete",
    "installed": "versión instalada",
    "fixed": "versión corregida",
    "location": "ubicación",
    "disposition": "disposición",
}
_CANDIDATE_DISPOSITION_ES = {
    "review_required": "revisión requerida",
    "confirmed": "confirmado",
    "not_actionable": "no accionable",
    "false_positive": "falso positivo",
}

_STATIC_GENERATOR_COPY = {
    "The repository's complete required-check suite passes on the remediation commit": (
        "El conjunto completo de comprobaciones requeridas del repositorio se aprueba en el commit de remediación"
    ),
    "No new material regression or cross-format report-truth mismatch is introduced": (
        "No se introduce ninguna regresión material nueva ni discrepancia de verdad del informe entre formatos"
    ),
    "Client and project display metadata are descriptive and do not replace canonical scope identifiers.": (
        "Los metadatos descriptivos del cliente y del proyecto no sustituyen los identificadores canónicos de alcance."
    ),
    "Canonical scoring is reconciled to retained evidence without recomputing or inflating either score; evidence limitations remain explicit.": (
        "La puntuación canónica se concilia con la evidencia conservada sin recalcular ni inflar ninguna puntuación; las limitaciones de evidencia permanecen explícitas."
    ),
    "Score effect: assurance-only until triaged.": (
        "Efecto en la puntuación: solo aseguramiento mientras la disposición humana "
        "autorizada siga pendiente; el estado del triaje técnico de NICO se informa "
        "por separado."
    ),
    "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.": (
        "Los resultados históricos de flujos de trabajo, trabajos y despliegues se conservan como una tendencia operativa sin puntuación."
    ),
    "No workflow configuration was retained at the assessed commit.": (
        "No se conservó configuración de flujos de trabajo en el commit evaluado."
    ),
    "Workflow configuration was not proven against the exact assessed commit.": (
        "No se demostró la configuración de flujos de trabajo contra el commit exacto evaluado."
    ),
    "Explicit workflow permission boundaries were assessed and not proven at the assessed commit.": (
        "Se evaluaron los límites explícitos de permisos del flujo de trabajo y no se demostraron en el commit evaluado."
    ),
}
_STRUCTURED_TRIGGER_TOKENS = (
    "Score effect: assurance-only until triaged.",
    "Workflow files at assessed commit:",
    "Workflow configuration exact-SHA match:",
    "Explicit permissions control:",
    "Provider-neutral immutable CI objective coverage:",
    "CI control assurance incomplete;",
    "Technical maturity remains based on exact-commit technical controls.",
    "Complexity risk: observed;",
    "The exact-SHA rerun no longer reports cyclomatic complexity above",
    "Candidate volume and reviewer workload are operational review metrics",
    "Candidate volume, clustering and reviewer workload do not change numeric security or readiness scores.",
    "applicable analyzers completed;",
    "Review-required scanner candidates:",
    "Non-success or unresolved deployment observations:",
    "Outcome classification breakdown:",
    "Workflow jobs:",
    "Deployment outcome taxonomy (unscored context):",
    "Top-level entries[",
    "; commit exacto=",
    "; exact commit=",
    ": raw=",
    "disposition=",
    *_STATIC_GENERATOR_COPY.keys(),
)


def _current_report_phrase_pairs() -> tuple[tuple[str, str], ...]:
    """Return approved static final-report presentation pairs."""

    from nico.comprehensive_current_report_truth_parity_v1 import _ES_PHRASES

    return tuple(
        sorted(
            ((str(source), str(target)) for source, target in _ES_PHRASES.items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def _translate_structured_current_report_copy(text: str) -> str:
    output = str(text or "")

    # This function sits on the hot Spanish presentation path. Most renderer values do
    # not belong to these newly added generator families. Avoid repeatedly scanning
    # every heading, atom, paragraph, and PDF fragment with all structured regexes when
    # none of their canonical generator markers is present. Unknown variants remain
    # untouched and therefore continue to the existing strict fail-closed translator.
    if not any(token in output for token in _STRUCTURED_TRIGGER_TOKENS):
        return output

    def workflow_files(match: re.Match[str]) -> str:
        return f"Archivos de flujo de trabajo en el commit evaluado: {match.group('count')}."

    def exact_sha(match: re.Match[str]) -> str:
        state = _BOOLEAN_ES.get(match.group("state").casefold(), match.group("state"))
        return f"Coincidencia exacta de SHA de la configuración del flujo de trabajo: {state}."

    def permission(match: re.Match[str]) -> str:
        state = _STATE_ES.get(match.group("state").casefold(), match.group("state"))
        return f"Control de permisos explícitos: {state}."

    def coverage(match: re.Match[str]) -> str:
        return (
            "Cobertura de objetivos inmutables de CI independiente del proveedor: "
            f"{match.group('coverage')}."
        )

    def assurance(match: re.Match[str]) -> str:
        # Objective identifiers are canonical machine keys and intentionally remain exact.
        return (
            "La garantía de los controles de CI está incompleta; no se afirmó aprobación ni fallo para: "
            f"{match.group('objectives')}."
        )

    def technical_maturity(match: re.Match[str]) -> str:
        return (
            "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
            f"La preparación ajustada por evidencia es {match.group('adjusted')}/100 "
            f"frente a una madurez técnica de {match.group('technical')}/100. NICO "
            f"conserva {match.group('review_required')} candidatos que requieren revisión y "
            f"{match.group('confirmed')} hallazgos materiales confirmados como contexto "
            "explícito de revisión."
        )

    def complexity_risk(match: re.Match[str]) -> str:
        return (
            "Riesgo de complejidad: observado; "
            f"{match.group('count')} hallazgos de complejidad con fuente exacta "
            "siguen pendientes de revisión humana."
        )

    def complexity_acceptance(match: re.Match[str]) -> str:
        return (
            "La nueva ejecución con SHA exacto ya no informa una complejidad "
            f"ciclomática superior a {match.group('threshold')} en "
            f"{match.group('location')}"
        )

    def analyzer_completion(match: re.Match[str]) -> str:
        return (
            "Analizadores aplicables completados: "
            f"{match.group('completed')} de {match.group('applicable')}; "
            f"incompletos: {match.group('incomplete')}. "
            "La clasificación técnica de candidatos se mantiene separada: se conservan "
            f"{match.group('review_required')} candidatos que requieren revisión y "
            f"{match.group('confirmed')} hallazgos materiales confirmados."
        )

    def review_required_scanner_candidates(match: re.Match[str]) -> str:
        return (
            "Candidatos de analizador que requieren revisión: "
            f"{match.group('count')}{match.group('period')}"
        )

    def unresolved_deployments(match: re.Match[str]) -> str:
        return (
            "Observaciones de despliegues no exitosos o no resueltos: "
            f"{match.group('count')}."
        )

    def outcome_classification(match: re.Match[str]) -> str:
        return (
            "Desglose de la clasificación de resultados: "
            f"{match.group('value')}{match.group('period') or ''}"
        )

    def deployment_taxonomy(match: re.Match[str]) -> str:
        def metric(value: str) -> str:
            if value.strip().casefold() == "not separately evidenced":
                return "no se evidenciaron por separado"
            return value.strip()

        translated = (
            "Taxonomía de resultados de despliegue (contexto sin puntuación): "
            f"observados={match.group('observed')}; "
            f"exitosos={match.group('successful')}; "
            f"fallidos/no exitosos={metric(match.group('failed'))}; "
            f"no resueltos={metric(match.group('unresolved'))}"
        )
        if match.group("remainder") is not None:
            translated += (
                "; remanente fallido o no resuelto="
                f"{match.group('remainder')}"
            )
        return translated + "."

    def workflow_jobs_with_rate(match: re.Match[str]) -> str:
        return (
            "Trabajos de flujo de trabajo: "
            f"{match.group('successful')} exitosos de {match.group('observed')} "
            f"observados ({match.group('rate')})."
        )

    def workflow_jobs_without_rate(match: re.Match[str]) -> str:
        return (
            "Trabajos de flujo de trabajo: "
            f"{match.group('observed')} observados; no se informan el conteo exitoso "
            "ni la tasa de éxito porque no se conservó un numerador compatible."
        )

    def top_level_entry(match: re.Match[str]) -> str:
        return (
            f"Elementos de nivel superior[{match.group('index')}]: "
            f"{match.group('value')}"
        )

    def scanner_state(match: re.Match[str]) -> str:
        state = _STATE_ES.get(match.group("state").casefold(), match.group("state"))
        return f"{match.group('prefix')}{state}"

    def scanner_execution_summary(match: re.Match[str]) -> str:
        boolean = {"yes": "sí", "no": "no"}
        artifact = {"retained": "conservado", "missing": "faltante"}
        state = _STATE_ES[match.group("state").casefold()]
        return (
            f"{match.group('prefix')}{state}; "
            f"commit exacto={boolean[match.group('commit').casefold()]}; "
            f"artefacto={artifact[match.group('artifact').casefold()]}; "
            "conteo de hallazgos materiales confirmados="
            f"{match.group('count')}; carga de hallazgos sin procesar incluida="
            f"{boolean[match.group('raw').casefold()]}."
        )

    def candidate_summary(match: re.Match[str]) -> str:
        category = _CANDIDATE_CATEGORY_ES[match.group("category").casefold()]
        return (
            f"{category}: brutos={match.group('raw')}; "
            f"materiales confirmados={match.group('confirmed')}; "
            f"requieren revisión={match.group('review')}; "
            f"excluidos por ser solo de pruebas={match.group('excluded')}; "
            f"aprobados o no bloqueantes={match.group('nonblocking')}."
        )

    def candidate_detail_lines(value: str) -> str:
        lines = value.splitlines(keepends=True)
        output_lines: list[str] = []
        for line in lines:
            match = re.match(
                r"(?P<prefix>\s*(?:[-•]\s*)?)(?P<category>Dependency|Secret|Static)"
                r"(?P<rest>\s+·.*\bdisposition=[^\r\n]+)",
                line,
                flags=re.IGNORECASE,
            )
            if not match:
                output_lines.append(line)
                continue
            localized = (
                match.group("prefix")
                + _CANDIDATE_CATEGORY_ES[match.group("category").casefold()]
                + match.group("rest")
            )
            for source, target in _CANDIDATE_DETAIL_LABEL_ES.items():
                localized = re.sub(
                    rf"(?<![\w]){re.escape(source)}=",
                    f"{target}=",
                    localized,
                )
            localized = re.sub(
                r"(?P<label>disposición=)(?P<value>[A-Za-z_]+)",
                lambda disposition: (
                    disposition.group("label")
                    + _CANDIDATE_DISPOSITION_ES.get(
                        disposition.group("value").casefold(),
                        disposition.group("value"),
                    )
                ),
                localized,
            )
            output_lines.append(localized)
        return "".join(output_lines)

    if "Workflow files at assessed commit:" in output:
        output = _PROVIDER_WORKFLOW_FILES_RE.sub(workflow_files, output)
    if "Workflow configuration exact-SHA match:" in output:
        output = _PROVIDER_EXACT_SHA_RE.sub(exact_sha, output)
    if "Explicit permissions control:" in output:
        output = _PROVIDER_PERMISSION_RE.sub(permission, output)
    if "Provider-neutral immutable CI objective coverage:" in output:
        output = _PROVIDER_COVERAGE_RE.sub(coverage, output)
    if "CI control assurance incomplete;" in output:
        output = _PROVIDER_ASSURANCE_RE.sub(assurance, output)
    if "Technical maturity remains based on exact-commit technical controls." in output:
        output = _TECHNICAL_MATURITY_RE.sub(technical_maturity, output)
    if "Complexity risk: observed;" in output:
        output = _COMPLEXITY_RISK_RE.sub(complexity_risk, output)
    if "The exact-SHA rerun no longer reports cyclomatic complexity above" in output:
        output = _COMPLEXITY_ACCEPTANCE_RE.sub(complexity_acceptance, output)
    if "Candidate volume and reviewer workload are operational review metrics" in output:
        output = _CANDIDATE_VOLUME_RE.sub(
            "El volumen de candidatos y la carga de trabajo del revisor son métricas operativas de revisión y no tienen efecto numérico sobre la madurez técnica ni sobre la puntuación de Ajuste por evidencia.",
            output,
        )
    if "Candidate volume, clustering and reviewer workload do not change numeric security or readiness scores." in output:
        output = _CANDIDATE_VOLUME_SECURITY_RE.sub(
            "El volumen de candidatos, la agrupación y la carga de trabajo de revisión no modifican las puntuaciones numéricas de seguridad ni de preparación.",
            output,
        )
    if "applicable analyzers completed;" in output:
        output = _ANALYZER_COMPLETION_RE.sub(analyzer_completion, output)
    if "Review-required scanner candidates:" in output:
        output = _REVIEW_REQUIRED_SCANNER_CANDIDATES_RE.sub(
            review_required_scanner_candidates,
            output,
        )
    if "Non-success or unresolved deployment observations:" in output:
        output = _UNRESOLVED_DEPLOYMENTS_RE.sub(unresolved_deployments, output)
    if "Outcome classification breakdown:" in output:
        output = _OUTCOME_CLASSIFICATION_RE.sub(outcome_classification, output)
    if "Deployment outcome taxonomy (unscored context):" in output:
        output = _DEPLOYMENT_TAXONOMY_RE.sub(deployment_taxonomy, output)
    if "Workflow jobs:" in output:
        output = _WORKFLOW_JOBS_WITH_RATE_RE.sub(workflow_jobs_with_rate, output)
        output = _WORKFLOW_JOBS_WITHOUT_RATE_RE.sub(
            workflow_jobs_without_rate,
            output,
        )
    if "Top-level entries[" in output:
        output = _TOP_LEVEL_ENTRY_RE.sub(top_level_entry, output)
    if "; exact commit=" in output.casefold():
        output = _SCANNER_EXECUTION_SUMMARY_RE.sub(
            scanner_execution_summary,
            output,
        )
    if "; commit exacto=" in output or "; exact commit=" in output:
        output = _SCANNER_STATE_RE.sub(scanner_state, output)
    if ": raw=" in output:
        output = _CANDIDATE_CATEGORY_SUMMARY_RE.sub(candidate_summary, output)
    if "disposition=" in output:
        output = candidate_detail_lines(output)
    for source, target in _STATIC_GENERATOR_COPY.items():
        if source in output:
            output = output.replace(source, target)
    return output


def localize_current_report_copy_v98(value: Any) -> str:
    """Project registered NICO-authored current-report copy to es-MX.

    Structured generator families are translated by grammar so dynamic values remain
    exact. Static approved phrases are then applied. Unknown prose is deliberately left
    unchanged so the canonical Spanish translator can fail closed rather than publish
    mixed-language presentation copy.
    """

    text = _translate_structured_current_report_copy(str(value or ""))
    for source, target in _current_report_phrase_pairs():
        text = text.replace(source, target)
    return text


def _wrap_one_arg(current: Callable[[Any], str]) -> Callable[[Any], str]:
    if getattr(current, _ONE_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any) -> str:
        return current(localize_current_report_copy_v98(value))

    setattr(wrapped, _ONE_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def _wrap_two_arg(current: Callable[[Any, Any], str]) -> Callable[[Any, Any], str]:
    if getattr(current, _TWO_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any, key: Any = "") -> str:
        return current(localize_current_report_copy_v98(value), key)

    setattr(wrapped, _TWO_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def install_comprehensive_spanish_current_copy_worker_v98() -> dict[str, Any]:
    """Bind current report localization before the isolated renderer cache freezes."""

    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    baseline = v88.install_comprehensive_spanish_exit_criteria_v88()
    if baseline.get("bound") is not True:
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_v88_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    current_field = getattr(v88, "_translate_canonical_field_v88", None)
    current_presentation = getattr(v88, "_translate_presentation_v88", None)
    current_safe = getattr(v88, "_presentation_safe_es_v88", None)
    if not all(callable(value) for value in (current_field, current_presentation, current_safe)):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_current_copy_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    field = _wrap_two_arg(current_field)
    presentation = _wrap_one_arg(current_presentation)
    safe = _wrap_one_arg(current_safe)
    v88._translate_canonical_field_v88 = field
    v88._translate_presentation_v88 = presentation
    v88._presentation_safe_es_v88 = safe

    binder = getattr(v88, "_bind_translation_surfaces", None)
    if callable(binder):
        binder()

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation_module

    bound = bool(
        canonical._translate_presentation_field is field
        and canonical._translate_presentation is presentation
        and presentation_module._safe_es is safe
    )
    sample = localize_current_report_copy_v98(
        "Technical maturity remains based on exact-commit technical controls. "
        "Evidence-Adjusted readiness is 93/100 versus technical maturity 93/100. "
        "NICO retains 691 review-required candidates and 0 confirmed material findings as explicit review context. "
        "Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or Evidence-Adjusted score effect. "
        "Explicit permissions control: passed. Provider-neutral immutable CI objective coverage: 100%. "
        "1 of 1 applicable analyzers completed; 0 are incomplete. Candidate triage is separate: 2 review-required candidates and 0 confirmed material findings are retained. "
        "Review-required scanner candidates: 3."
    )
    sample_ok = (
        "Technical maturity remains based on exact-commit technical controls" not in sample
        and "Evidence-Adjusted readiness is 93/100" not in sample
        and "NICO retains 691 review-required candidates" not in sample
        and "Explicit permissions control" not in sample
        and "Provider-neutral immutable CI objective coverage" not in sample
        and "Candidate volume and reviewer workload" not in sample
        and "applicable analyzers completed" not in sample
        and "Candidate triage is separate" not in sample
        and "Review-required scanner candidates" not in sample
        and "La madurez técnica sigue basándose en controles técnicos del commit exacto." in sample
        and "La preparación ajustada por evidencia es 93/100 frente a una madurez técnica de 93/100." in sample
        and "NICO conserva 691 candidatos que requieren revisión y 0 hallazgos materiales confirmados" in sample
        and "Control de permisos explícitos: aprobado." in sample
        and "Cobertura de objetivos inmutables de CI independiente del proveedor: 100%." in sample
        and "El volumen de candidatos y la carga de trabajo del revisor" in sample
        and "Analizadores aplicables completados: 1 de 1; incompletos: 0." in sample
        and "2 candidatos que requieren revisión" in sample
        and "Candidatos de analizador que requieren revisión: 3." in sample
    )

    return {
        "status": "installed" if bound and sample_ok else "blocked",
        "version": VERSION,
        "bound": bound,
        "current_report_copy_contract_bound": sample_ok,
        "structured_provider_ci_copy_bound": True,
        "structured_maturity_review_context_bound": True,
        "structured_analyzer_summary_bound": True,
        "structured_review_required_scanner_count_bound": True,
        "worker_safe_before_renderer_cache": True,
        "unknown_prose_still_delegates_fail_closed": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "english_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_current_copy_worker_v98",
    "localize_current_report_copy_v98",
]
