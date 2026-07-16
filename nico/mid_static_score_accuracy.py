from __future__ import annotations

from functools import wraps
from typing import Any, Callable

MID_STATIC_SCORE_ACCURACY_VERSION = "nico.mid_static_score_accuracy.v4"
_MARKER = "_nico_mid_static_score_accuracy_v4"
_INSTALLED_WRAPPER: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


def _set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def _status(score: int) -> str:
    return "green" if score >= 80 else "yellow" if score >= 55 else "red"


def install_mid_static_score_accuracy() -> dict[str, Any]:
    """Credit and disclose TypeScript compiler evidence as static analysis.

    The controlled Mid scanner requests TypeScript, but the legacy static score
    counted Bandit, Semgrep, and ESLint only. This patch applies the same bounded
    execution credits and penalties to TypeScript without treating execution as a
    clean result or changing any parsed finding.

    Installation uses function identity rather than an inherited marker. Several
    NICO compatibility wrappers use ``functools.wraps`` and can copy marker
    attributes even when they later replace the active score function. Re-entry
    therefore restores this accuracy boundary around the final active function.
    """

    global _INSTALLED_WRAPPER

    from nico import full_assessment_scorecard as scorecard

    current: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = scorecard._static_section
    if _INSTALLED_WRAPPER is not None and current is _INSTALLED_WRAPPER:
        return {"status": "already_installed", "version": MID_STATIC_SCORE_ACCURACY_VERSION}

    @wraps(current)
    def static_section_with_typescript(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
        # Capture the exact scanner contract before invoking downstream scoring.
        # Compatibility layers may normalize or narrow tool lists in place; that
        # must not erase the evidence that TypeScript was requested or completed.
        run = _set(scanner.get("tools_run"))
        requested = _set(scanner.get("tools_requested"))
        unavailable = _set(scanner.get("unavailable_tools"))
        failed = _set(scanner.get("failed_tools"))
        timed_out = _set(scanner.get("timed_out_tools"))

        delta = 0
        state = "not_requested"
        if "typescript" in run:
            delta = 10
            state = "completed"
        elif "typescript" in failed:
            delta = -12
            state = "failed"
        elif "typescript" in timed_out:
            delta = -8
            state = "timed_out"
        elif "typescript" in unavailable:
            delta = -5
            state = "unavailable"
        elif "typescript" in requested:
            state = "requested_without_terminal_evidence"

        section = current(repo, scanner)
        previous = int(section.get("score") or 0)
        breakdown = section.setdefault("score_evidence_breakdown", {})
        prior_post = breakdown.get("post_typescript_score")
        prior_state = str(breakdown.get("typescript_state") or "")
        prior_delta = breakdown.get("typescript_score_adjustment")
        already_preserved = (
            breakdown.get("typescript_accuracy_applied") is True
            and prior_state == state
            and prior_delta == delta
            and prior_post == previous
        )
        if already_preserved:
            return section

        # A later compatibility layer may retain our breakdown while resetting or
        # recomputing the score. In that case, reapply the bounded delta to the
        # final active score rather than trusting a copied marker alone.
        revised = max(0, min(88, previous + delta))
        section["score"] = revised
        section["status"] = _status(revised)
        evidence = section.setdefault("evidence", [])
        note = f"TypeScript compiler static-analysis state={state}; bounded score adjustment={delta:+d}."
        if note not in evidence:
            evidence.append(note)
        section["verified_claims"] = list(evidence)
        breakdown.update(
            {
                "pre_typescript_score": previous,
                "typescript_state": state,
                "typescript_score_adjustment": delta,
                "post_typescript_score": revised,
                "typescript_execution_treated_as_clean": False,
                "typescript_accuracy_applied": True,
                "typescript_state_captured_before_downstream_normalization": True,
                "typescript_reapplied_after_score_rewrite": prior_post is not None and prior_post != previous,
                "version": MID_STATIC_SCORE_ACCURACY_VERSION,
            }
        )
        if state in {"failed", "timed_out", "unavailable", "requested_without_terminal_evidence"}:
            finding = f"TypeScript static-analysis execution {state.replace('_', ' ')}; typed-code conclusions remain incomplete."
            findings = section.setdefault("findings", [])
            if finding not in findings:
                findings.append(finding)
        return section

    setattr(static_section_with_typescript, _MARKER, True)
    setattr(static_section_with_typescript, "_nico_previous", current)
    scorecard._static_section = static_section_with_typescript
    _INSTALLED_WRAPPER = static_section_with_typescript
    return {
        "status": "installed",
        "version": MID_STATIC_SCORE_ACCURACY_VERSION,
        "typescript_counted_as_static_analysis": True,
        "typescript_state_captured_before_downstream_normalization": True,
        "execution_treated_as_clean": False,
        "finding_truth_changed": False,
        "score_forced_upward": False,
        "final_active_function_wrapped": True,
        "copied_marker_trusted_as_installation_proof": False,
        "human_review_required": True,
    }


__all__ = ["MID_STATIC_SCORE_ACCURACY_VERSION", "install_mid_static_score_accuracy"]
