from __future__ import annotations

from typing import Any, Mapping

VERSION = "nico.candidate-phase1-report-workload-text.v1"
_HEAVY = {"pdf_base64", "html", "markdown", "scanner_results", "raw_output", "stdout", "stderr"}


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _find(node: Any, name: str, depth: int = 0) -> Mapping[str, Any]:
    if depth > 10:
        return {}
    if isinstance(node, Mapping):
        direct = node.get(name)
        if isinstance(direct, Mapping):
            return direct
        for key, value in node.items():
            if str(key).casefold() in _HEAVY:
                continue
            found = _find(value, name, depth + 1)
            if found:
                return found
    elif isinstance(node, list) and len(node) <= 500:
        for value in node:
            found = _find(value, name, depth + 1)
            if found:
                return found
    return {}


def workload_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    triage = _find(canonical, "technical_triage")
    metrics = triage.get("workload_metrics") if isinstance(triage.get("workload_metrics"), Mapping) else {}
    if not metrics:
        return ""
    if spanish:
        lines = [
            "## Triage técnico automatizado y carga de revisión",
            "",
            f"- Cobertura: {_integer(metrics.get('technical_triage_completed'))}/{_integer(metrics.get('total_candidates'))} ({metrics.get('technical_triage_coverage_pct', 0)}%).",
            f"- Análisis estable conservado: {_integer(metrics.get('stable_carry_forward_count'))}.",
            f"- Nuevo triaje técnico: {_integer(triage.get('fresh_technical_triage_completed'))}.",
            f"- Atención humana individual: {_integer(metrics.get('candidates_requiring_individual_human_attention'))}.",
            f"- Grupos de revisión humana: {_integer(metrics.get('grouped_review_cluster_count'))}, cubriendo {_integer(metrics.get('grouped_human_review_candidate_count'))} candidatos.",
            f"- Unidades de trabajo humano: {_integer(metrics.get('human_review_work_units'))}.",
            "- La disposición y aprobación humanas siguen pendientes.",
        ]
    else:
        lines = [
            "## Automated Technical Triage and Reviewer Workload",
            "",
            f"- Technical-triage coverage: {_integer(metrics.get('technical_triage_completed'))}/{_integer(metrics.get('total_candidates'))} ({metrics.get('technical_triage_coverage_pct', 0)}%).",
            f"- Stable carry-forward: {_integer(metrics.get('stable_carry_forward_count'))}.",
            f"- Fresh technical triage: {_integer(triage.get('fresh_technical_triage_completed'))}.",
            f"- Individual human attention: {_integer(metrics.get('candidates_requiring_individual_human_attention'))}.",
            f"- Grouped human-review clusters: {_integer(metrics.get('grouped_review_cluster_count'))}, covering {_integer(metrics.get('grouped_human_review_candidate_count'))} candidates.",
            f"- Human review work units: {_integer(metrics.get('human_review_work_units'))}.",
            "- Human disposition and approval remain pending.",
        ]
    return "\n".join(lines)


def rewrite_compact_markdown(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
    replacements = {
        "Assurance-only until triaged": "Human disposition pending; NICO technical triage complete",
        "Score effect: assurance-only until triaged.": "Score effect: assurance-only while human disposition remains pending; NICO technical triage is complete.",
        "Triage review-required candidates using retained scanner artifacts.": "Review routed exceptions and eligible grouped-review clusters using retained scanner artifacts; preserve explicit dispositions for all underlying candidate IDs.",
        "Efecto en puntuación: solo aseguramiento hasta completar la revisión.": "Efecto en puntuación: solo aseguramiento mientras la disposición humana siga pendiente; el triaje técnico de NICO está completo.",
        "Revisar candidatos pendientes usando los artefactos conservados.": "Revisar excepciones enrutadas y grupos elegibles usando los artefactos conservados; conservar disposiciones explícitas para todos los candidatos subyacentes.",
    }
    for old, new in replacements.items():
        markdown = markdown.replace(old, new)
    workload = workload_markdown(canonical, spanish=spanish)
    if workload and workload not in markdown:
        heading = "## Puerta de revisión humana y aceptación" if spanish else "## Human Review and Acceptance Gate"
        if heading in markdown:
            markdown = markdown.replace(heading, workload + "\n\n" + heading, 1)
        else:
            markdown = markdown.rstrip() + "\n\n" + workload + "\n"
    return markdown


__all__ = ["VERSION", "rewrite_compact_markdown", "workload_markdown"]
