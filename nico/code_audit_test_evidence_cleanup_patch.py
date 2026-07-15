from __future__ import annotations

from typing import Any, Callable

PATCH_VERSION = "nico.code_audit_test_evidence_cleanup.v1"
_MARKER = "_nico_code_audit_test_evidence_cleanup_v1"
_STALE_ABSENCE_FRAGMENTS = (
    "no test-path signals were found in fetched text files",
    "no test path signals were found in fetched text files",
)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in _list(result.get("sections")):
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _remove_stale_absence_claims(items: Any) -> list[Any]:
    values = items if isinstance(items, list) else ([] if items in (None, "") else [items])
    return [
        item
        for item in values
        if not any(fragment in str(item or "").lower() for fragment in _STALE_ABSENCE_FRAGMENTS)
    ]


def clean_code_audit_test_evidence(result: dict[str, Any]) -> bool:
    """Remove only the contradicted standalone no-test claim.

    A bounded fetched-text sample may legitimately contain zero test paths, so the
    aggregate metrics line containing ``test-path signals=0`` is retained. The
    standalone repository-wide absence sentence is removed only when positive
    recursive-tree test evidence exists in the same report.
    """

    from nico.final_score_reconciliation_patch import _test_path_count

    test_count = _test_path_count(result)
    code = _section(result, "code_audit")
    if test_count <= 0 or not code:
        return False

    changed = False
    for key in (
        "evidence",
        "findings",
        "unavailable",
        "verified_claims",
        "unverified_claims",
    ):
        before = code.get(key)
        after = _remove_stale_absence_claims(before)
        normalized_before = before if isinstance(before, list) else ([] if before in (None, "") else [before])
        if after != normalized_before:
            changed = True
        code[key] = after

    code.setdefault("evidence", [])
    reconciliation_note = (
        f"Test evidence reconciled across scopes: the recursive repository tree contains {test_count} "
        "test-path signal(s). A bounded fetched-text sample with zero test paths is not treated as "
        "repository-wide absence evidence."
    )
    if reconciliation_note not in code["evidence"]:
        code["evidence"].append(reconciliation_note)
        changed = True

    code["verified_claims"] = list(code.get("evidence") or [])
    code["unverified_claims"] = list(code.get("unavailable") or [])
    return changed


def install_code_audit_test_evidence_cleanup_patch() -> dict[str, Any]:
    from nico import final_score_reconciliation_patch as reconciliation

    current: Callable[[dict[str, Any]], bool] = reconciliation.reconcile_code_audit_test_evidence
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "standalone_absence_claim_removed": True,
            "bounded_sample_metrics_preserved": True,
        }
    original = current

    def reconcile_with_cleanup(result: dict[str, Any]) -> bool:
        changed = bool(original(result))
        return clean_code_audit_test_evidence(result) or changed

    setattr(reconcile_with_cleanup, _MARKER, True)
    setattr(reconcile_with_cleanup, "_nico_previous", original)
    reconciliation.reconcile_code_audit_test_evidence = reconcile_with_cleanup
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "standalone_absence_claim_removed": True,
        "bounded_sample_metrics_preserved": True,
        "score_change_allowed": False,
        "guardrail": (
            "The cleanup removes only a standalone no-test claim contradicted by positive recursive-tree evidence. "
            "It preserves bounded-sample metrics, all unrelated findings, human review, and client-ready controls."
        ),
    }


__all__ = [
    "PATCH_VERSION",
    "clean_code_audit_test_evidence",
    "install_code_audit_test_evidence_cleanup_patch",
]
