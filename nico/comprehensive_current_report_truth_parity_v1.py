from __future__ import annotations

import html
import io
import re
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader


VERSION = "nico.comprehensive-current-report-truth-parity.v1.9"
_OUTLINE_MARKER = "__nico_current_report_truth_outline_v1__"
_CI_MARKER = "__nico_current_report_truth_ci_v1__"
_VALIDATION_MARKER = "__nico_current_report_truth_validation_v1__"
_REVIEW_LOCALIZATION_MARKER = "__nico_current_report_truth_review_localization_v1__"
_DYNAMIC_LOCALIZER_MARKER = "__nico_current_report_truth_dynamic_localizer_v1__"

_ES_EXACT = {
    "Exceptional": "Excepcional",
    "Code audit": "Auditoría de código",
    "Code Audit": "Auditoría de código",
    "Cybersecurity specialist": "Especialista en ciberseguridad",
}

_ES_PHRASES = {
    "Review-Required Candidate Register": "Registro de candidatos que requieren revisión",
    "Material confirmado findings": "Hallazgos materiales confirmados",
    "verificada material findings": "hallazgos materiales verificados",
    "Confirmed material findings": "Hallazgos materiales confirmados",
    "Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.": (
        "Se analizaron las señales ejecutables del código fuente del commit exacto sin convertir comentarios, cadenas, "
        "definiciones de detectores, ejemplos ni pruebas en defectos."
    ),
    "Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.": (
        "Los manifiestos autoritativos y la evidencia contextual de dependencias se conciliaron por paquete, versión instalada, "
        "aviso, versión corregida, ruta, alcance y accesibilidad."
    ),
    "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.": (
        "La evidencia de secretos con conocimiento del historial se separó en hallazgos materiales verificados, candidatos que requieren "
        "revisión, marcadores explícitos de ejemplo y observaciones ajenas a producción."
    ),
    "Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.": (
        "La capacidad de entrega sostenible se deriva de la mantenibilidad inmutable de la arquitectura y la automatización de los flujos "
        "de trabajo; el volumen de actividad mutable es contexto sin puntuación."
    ),
    "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.": (
        "Reforzar los límites de arquitectura, la automatización de pruebas y publicaciones, la evidencia de QA funcional y la verificación de remediaciones."
    ),
    "Non-success deployment classification": "Clasificación de despliegues no exitosos",
    "Not available": "No disponible",
    "Job success rate": "Tasa de éxito de trabajos",
    "Successful workflow runs": "Ejecuciones exitosas de flujos de trabajo",
    "Non-success workflow runs": "Ejecuciones no exitosas de flujos de trabajo",
    "Jobs observed": "Trabajos observados",
    "Jobs observado": "Trabajos observados",
    "Deployments observed": "Despliegues observados",
    "Deployments observado": "Despliegues observados",
    "Successful deployments": "Despliegues exitosos",
    "Non-success deployments": "Despliegues no exitosos",
    "Cybersecurity specialist": "Especialista en ciberseguridad",
    "Code audit": "Auditoría de código",
    "Code Audit": "Auditoría de código",
    "Exceptional": "Excepcional",
    "immutable native-control vector=not applicable; provider-neutral objective coverage is reported separately.": (
        "vector inmutable de controles nativos=no aplica; la cobertura de objetivos neutral al proveedor se informa por separado."
    ),
}

_SPANISH_LEAK_MARKERS = (
    "Review-Required Candidate Register",
    "Material confirmado findings",
    "verificada material findings",
    "Strengthen architecture boundaries",
    "Sustainable delivery capacity is derived",
    "Exact-commit executable source signals were analyzed",
    "Authoritative manifests and contextual dependency evidence were reconciled",
    "History-aware secret evidence was separated",
    "Non-success deployment classification",
    "Job success rate",
    "Successful workflow runs",
    "Non-success workflow runs",
    "Jobs observado",
    "Deployments observado",
    "Successful deployments",
    "Non-success deployments",
    "Explicit permissions control",
    "Provider-neutral immutable CI objective coverage",
    "Candidate volume and reviewer workload are operational review metrics",
    "Cybersecurity specialist",
    "maturity_level: Exceptional",
)

# Late report-owned fields must fail closed even when an unforeseen English sentence
# falls outside the older two-keyword heuristic. These are language signals, not
# translation allowlists. Protected technical atoms and explicitly tagged provenance
# evidence are handled before this detector runs.
_ENGLISH_PRESENTATION_WORDS = frozenset(
    {
        "after",
        "against",
        "and",
        "approved",
        "are",
        "at",
        "available",
        "before",
        "blocked",
        "cannot",
        "client",
        "closed",
        "completed",
        "could",
        "did",
        "does",
        "failed",
        "fail",
        "from",
        "has",
        "have",
        "human",
        "into",
        "is",
        "missing",
        "must",
        "new",
        "not",
        "only",
        "or",
        "pending",
        "prose",
        "renderer",
        "report",
        "required",
        "requires",
        "retained",
        "review",
        "reviewed",
        "sentence",
        "should",
        "supplied",
        "the",
        "this",
        "unavailable",
        "unexpected",
        "unregistered",
        "until",
        "verified",
        "was",
        "were",
        "while",
        "with",
        "without",
        "workflow",
        "would",
    }
)
_SPANISH_PRESENTATION_WORDS = frozenset(
    {
        "a",
        "al",
        "antes",
        "aprobado",
        "aprobada",
        "como",
        "con",
        "de",
        "del",
        "después",
        "el",
        "en",
        "esta",
        "este",
        "evidencia",
        "fue",
        "fueron",
        "hasta",
        "la",
        "las",
        "los",
        "no",
        "o",
        "para",
        "pendiente",
        "por",
        "que",
        "requiere",
        "requieren",
        "revisión",
        "se",
        "sin",
        "son",
        "un",
        "una",
        "y",
    }
)
_ENGLISH_MORPHOLOGY_RE = re.compile(
    r"(?:ing|ed|tion|ment|ness|lessly|fully|ize|ized|izes|ization)$",
    re.IGNORECASE,
)
_EXPLICIT_PROVENANCE_PREFIX_RE = re.compile(
    r"^(?:commit(?:[_ ]message)?|pull(?:[_ -]?request)?[_ ]title|"
    r"release[_ ]title|external[_ ]title|source[_ ]title)\s*:\s*",
    re.IGNORECASE,
)


def _text(value: Any, limit: int = 500000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    language = _text(
        identity.get("report_language")
        or identity.get("requested_report_language")
        or canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale"),
        40,
    ).casefold()
    return language.startswith("es")


def _visible_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _is_explicit_external_provenance(value: Any, key: str) -> bool:
    """Preserve deliberately tagged external source titles/messages byte-for-byte."""

    return str(key or "").casefold() == "evidence" and bool(
        _EXPLICIT_PROVENANCE_PREFIX_RE.match(str(value or "").strip())
    )


def _looks_like_unregistered_english_presentation(value: Any, key: str) -> bool:
    """Conservative fail-closed detector for late renderer-owned human prose.

    The canonical translator remains the primary authority. This detector closes the
    residual class where a long, clearly English sentence contains too few words from
    the legacy signal regex to trip its two-hit threshold. It deliberately avoids
    technical atoms and explicitly tagged provenance before invocation.
    """

    text = str(value or "").strip()
    words = [word.casefold() for word in re.findall(r"[A-Za-z]+", text)]
    if not words:
        return False

    from nico import comprehensive_spanish_canonical_report_v87 as canonical_spanish

    if canonical_spanish._looks_like_untranslated_english(text):
        return True

    english_hits = sum(word in _ENGLISH_PRESENTATION_WORDS for word in words)
    spanish_hits = sum(word in _SPANISH_PRESENTATION_WORDS for word in words)
    morphology_hits = sum(bool(_ENGLISH_MORPHOLOGY_RE.search(word)) for word in words)

    if str(key or "").casefold() == "label":
        return spanish_hits == 0 and english_hits >= 1 and len(words) <= 5

    # Mixed Spanish/English prose still fails when the English signal is substantial.
    if spanish_hits:
        return english_hits >= 3

    if english_hits >= 2:
        return True
    if len(words) >= 6 and (english_hits >= 1 or morphology_hits >= 2):
        return True
    return False


def assert_spanish_client_copy_is_localized(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    """Reject known NICO-authored English leakage on final es-MX surfaces.

    Dynamic report-owned fields are required to pass the strict field/source-aware
    presentation projection before rendering. This final surface check is intentionally
    not a recursive scan of the pre-projection canonical payload because canonical state
    may truthfully contain English source/presentation inputs before locale projection.
    """

    if not _is_spanish(canonical):
        return
    combined = "\n".join((markdown, _visible_html(rendered_html), _pdf_text(pdf)))
    lowered = combined.casefold()
    leaked = [marker for marker in _SPANISH_LEAK_MARKERS if marker.casefold() in lowered]
    if leaked:
        raise ValueError(
            "Spanish Comprehensive report retained NICO-authored English presentation copy: "
            + ", ".join(leaked)
        )


def normalize_ci_presentation_lines(lines: list[str]) -> list[str]:
    """Do not render an empty legacy native-control vector as a failing 0/0 result."""

    output: list[str] = []
    for line in lines:
        rendered = re.sub(
            r"immutable controls=0/0\.",
            "immutable native-control vector=not applicable; provider-neutral objective coverage is reported separately.",
            str(line),
            flags=re.IGNORECASE,
        )
        output.append(rendered)
    return output


def _install_semantic_manifest_authority() -> bool:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import comprehensive_spanish_presentation_parity_v1 as spanish
    from nico.comprehensive_report_semantic_manifest_v1 import (
        CANONICAL_TOC_TITLES,
        SECTION_TITLE_ES_BY_EN,
    )

    cleanup._TOC_TITLES = tuple(CANONICAL_TOC_TITLES)
    spanish._TITLE_MAP.clear()
    spanish._TITLE_MAP.update(SECTION_TITLE_ES_BY_EN)
    return bool(
        cleanup._TOC_TITLES == tuple(CANONICAL_TOC_TITLES)
        and tuple(spanish._TITLE_MAP) == tuple(SECTION_TITLE_ES_BY_EN)
    )


def _install_outline_matching() -> bool:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current = cleanup._outline_title
    if getattr(current, _OUTLINE_MARKER, False):
        return True

    @wraps(current)
    def outline_title(text: str) -> str:
        resolved = current(text)
        if resolved != "Report page":
            return resolved
        raw = str(text or "")
        for title in cleanup._TOC_TITLES:
            match = re.search(
                rf"(?mi)^\s*{re.escape(title)}\s*$",
                raw,
            )
            if match:
                return title
        return resolved

    setattr(outline_title, _OUTLINE_MARKER, True)
    setattr(outline_title, "_nico_previous", current)
    cleanup._outline_title = outline_title
    return True


def _install_spanish_phrase_completion() -> bool:
    from nico import comprehensive_spanish_presentation_parity_v1 as spanish

    # Keep current-report static copy on the existing bounded v98/current-presentation
    # boundary. Do not append it into v87's global replacement tuple: v87 is invoked on
    # full Markdown and every PDF text operand, so expanding that hot global loop makes
    # report generation scale with unrelated current-copy phrases. v98 reads this same
    # phrase contract dynamically before v87 and unknown copy still falls through to
    # v87's strict fail-closed translator.
    spanish._ES_EXTRA_EXACT.update(_ES_EXACT)
    spanish._ES_PHRASES.update(_ES_PHRASES)
    return True


def strict_spanish_presentation_v1(value: Any, key: str = "summary") -> str:
    """Strict field/source-aware projection for late renderer-owned es-MX copy.

    Protected technical/source atoms stay exact. Explicitly tagged external provenance
    remains byte-for-byte exact. Structured current-report generator copy is projected
    first. The canonical field translator then gets first authority over complete
    registered sentences, preventing permissive word replacement from corrupting an
    exact translation into mixed language. A conservative late language detector rejects
    residual unknown English renderer copy that the legacy heuristic does not recognize.
    """

    from nico import comprehensive_spanish_canonical_report_v87 as canonical_spanish
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation
    from nico.comprehensive_spanish_current_copy_worker_v98 import (
        localize_current_report_copy_v98,
    )

    raw = str(value or "")
    if presentation._looks_like_source_atom(raw):
        return raw
    if _is_explicit_external_provenance(raw, key):
        return raw

    prepared = localize_current_report_copy_v98(raw)
    strict_key = "label" if key == "status" else str(key or "summary")
    translated = canonical_spanish._translate_presentation_field(prepared, strict_key)
    rendered = presentation._safe_es(translated)
    if _looks_like_unregistered_english_presentation(rendered, strict_key):
        raise ValueError(
            f"missing Spanish presentation translation for {strict_key}: {raw[:180]}"
        )
    return rendered


def _install_review_companion_localization() -> bool:
    """Strictly localize dynamic review-companion copy after late reconstruction."""

    from nico import comprehensive_client_review_companion_v2 as companion

    # The companion historically ended its exact late-phrase pass with permissive
    # `_safe_es`, which can translate one English word inside an otherwise registered
    # full sentence. Preserve its explicit dynamic phrase ownership but remove that
    # partial-word cleanup. The field-aware wrapper below remains the fail-closed
    # authority for every renderer-owned field.
    current_dynamic = companion._localize_spanish_dynamic
    if not getattr(current_dynamic, _DYNAMIC_LOCALIZER_MARKER, False):

        @wraps(current_dynamic)
        def bounded_dynamic(value: Any) -> str:
            text = companion._text(value, 12000)
            for source, target in sorted(
                companion._SPANISH_DYNAMIC_PHRASES.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                text = text.replace(source, target)
            return text

        setattr(bounded_dynamic, _DYNAMIC_LOCALIZER_MARKER, True)
        setattr(bounded_dynamic, "_nico_previous", current_dynamic)
        companion._localize_spanish_dynamic = bounded_dynamic

    current = companion.review_sections
    if getattr(current, _REVIEW_LOCALIZATION_MARKER, False):
        return True

    @wraps(current)
    def review_sections(canonical: Mapping[str, Any], *, spanish: bool) -> list[dict[str, Any]]:
        sections = list(current(canonical, spanish=spanish))
        if not spanish:
            return sections
        localized: list[dict[str, Any]] = []
        for raw in sections:
            item = dict(raw)
            for field in ("status", "summary"):
                if item.get(field) not in (None, ""):
                    item[field] = strict_spanish_presentation_v1(item[field], field)
            for field in ("evidence", "findings", "limitations"):
                values = item.get(field)
                if isinstance(values, list):
                    item[field] = [
                        strict_spanish_presentation_v1(value, field) for value in values
                    ]
            localized.append(item)
        return localized

    setattr(review_sections, _REVIEW_LOCALIZATION_MARKER, True)
    setattr(review_sections, "_nico_previous", current)
    companion.review_sections = review_sections
    return True


def _install_ci_presentation_truth() -> bool:
    from nico import comprehensive_client_truth_final_v1 as client_truth

    current = client_truth._ci_lines
    if getattr(current, _CI_MARKER, False):
        return True

    @wraps(current)
    def ci_lines(canonical: Mapping[str, Any]) -> list[str]:
        return normalize_ci_presentation_lines(list(current(canonical)))

    setattr(ci_lines, _CI_MARKER, True)
    setattr(ci_lines, "_nico_previous", current)
    client_truth._ci_lines = ci_lines
    return True


def _install_final_spanish_leak_gate() -> bool:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current = cleanup.assert_human_review_package_cleanup
    if getattr(current, _VALIDATION_MARKER, False):
        return True

    @wraps(current)
    def validate(
        canonical: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> None:
        current(canonical, markdown, rendered_html, pdf)
        assert_spanish_client_copy_is_localized(
            canonical,
            markdown,
            rendered_html,
            pdf,
        )

    setattr(validate, _VALIDATION_MARKER, True)
    setattr(validate, "_nico_previous", current)
    cleanup.assert_human_review_package_cleanup = validate
    return True


def install_comprehensive_current_report_truth_parity_v1() -> dict[str, Any]:
    """Close current EN/es-MX presentation defects without changing canonical truth."""

    manifest = _install_semantic_manifest_authority()
    outline = _install_outline_matching()
    spanish = _install_spanish_phrase_completion()
    review_localization = _install_review_companion_localization()
    ci = _install_ci_presentation_truth()
    validation = _install_final_spanish_leak_gate()
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_semantic_report_manifest": manifest,
        "case_insensitive_toc_matching": outline,
        "spanish_embedded_phrase_localization": spanish,
        "late_review_companion_localization": review_localization,
        "late_review_partial_word_translation_disabled": True,
        "late_unknown_english_detector": True,
        "explicit_external_provenance_preserved": True,
        "unknown_report_owned_review_copy_fails_closed": True,
        "raw_canonical_truth_is_not_misclassified_as_final_presentation": True,
        "empty_native_ci_vector_not_rendered_as_zero_over_zero": ci,
        "final_spanish_leak_gate": validation,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_spanish_client_copy_is_localized",
    "install_comprehensive_current_report_truth_parity_v1",
    "normalize_ci_presentation_lines",
    "strict_spanish_presentation_v1",
]
