"""Read-only summaries of verified, identity-bound scanner provenance. No scoring."""
from collections.abc import Mapping
import re

_COMPLETE = {"complete", "completed", "completed_clean", "completed_with_findings"}


def outcomes(assessment, identity=None):
    provenance = assessment.get("nico_release_provenance")
    if not isinstance(provenance, Mapping):
        return None
    evidence = provenance.get("scanner_execution_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("verification_status") != "verified":
        return None
    if not evidence.get("run_id") or not evidence.get("commit_sha"):
        return None
    if (evidence["run_id"] != provenance.get("assessment_run_id")
            or evidence["commit_sha"] != provenance.get("assessed_repository_commit")):
        return None
    if any(assessment[k] != evidence.get(k) for k in ("repository", "run_id", "commit_sha") if k in assessment):
        return None
    if identity is not None and any(identity.get(k) != evidence.get(k)
            for k in ("run_id", "commit_sha", "repository")):
        return None
    rows = evidence.get("scanner_records")
    if not isinstance(rows, list) or not rows or evidence.get("selected_scanner"):
        return None
    grouped = {k: [] for k in ("current", "ci", "failed", "timed_out", "other")}
    seen = set()
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        name, status = row.get("scanner_name"), row.get("execution_status")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", name) or name in seen:
            return None
        seen.add(name)
        if row.get("inapplicability_evidence_verified") is True and row.get("applicable") is False:
            continue
        native = row.get("execution_evidence_verified") is True and row.get("execution_observed") is True
        retained = row.get("retained_ci_evidence_verified") is True and row.get("execution_observed") is False
        group = ("current" if native and status in _COMPLETE else
                 "ci" if retained and status in _COMPLETE else
                 status if native and status in ("failed", "timed_out") else "other")
        grouped[group].append(name)
    return grouped


def failed_scan_boundary(spanish):
    return ("Un análisis fallido o con tiempo agotado no demuestra la ausencia de hallazgos."
            if spanish else "A failed or timed-out scan does not establish the absence of findings.")


def summary(grouped, spanish):
    if grouped is None:
        return ("Consulte los registros de cada analizador para conocer su resultado."
                if spanish else "See individual scanner records for execution outcomes.")
    parts = []
    for key, en, es in [
        ("current", "completed in this run", "completados en esta ejecución"),
        ("ci", "verified exact-commit CI results (not rerun)", "resultados de CI verificados para el commit (sin nueva ejecución)"),
        ("failed", "failed in this run", "fallidos en esta ejecución"),
        ("timed_out", "timed out in this run", "sin completar por tiempo agotado"),
        ("other", "other or unclassified", "otros o sin clasificar"),
    ]:
        names = grouped[key]
        if names:
            parts.append(f"{es if spanish else en}: {len(names)}" +
                         (f" ({', '.join(names)})" if key != "current" else ""))
    if not parts:
        return ("Ningún resultado aplicable." if spanish else "No applicable scanner outcomes.")
    text = ("Analizadores: " if spanish else "Scanners: ") + "; ".join(parts) + "."
    if grouped["failed"] or grouped["timed_out"]:
        text += " " + failed_scan_boundary(spanish)
    return text
