"""Distinguish structured work packages from replaceable finding mirrors."""
from collections.abc import Mapping
from typing import Any
import re


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_work_package(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    identity = value.get("package_id") or value.get("work_package_id")
    if not _nonempty_text(identity):
        return False
    # Retained producer packages bind explicit source records and planning scope.
    binding = value.get("source_binding")
    refs = value.get("source_refs")
    if (re.fullmatch(r"NICO-WORK-[0-9A-F]{16}", identity)
            and isinstance(value.get("kind"), str) and value.get("kind") in {"finding_review_and_remediation", "evidence_gap_resolution", "candidate_disposition"}
            and isinstance(binding, Mapping)
            and all(_nonempty_text(binding.get(key)) for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id"))
            and isinstance(refs, list) and bool(refs)
            and all(isinstance(ref, Mapping) and _nonempty_text(ref.get("surface"))
                    and isinstance(ref.get("record_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", ref["record_sha256"]) for ref in refs)
            and _nonempty_text(value.get("action"))
            and isinstance(value.get("dependencies"), list)):
        return True
    # The earlier decision-grade contract uses related IDs and ordered steps.
    return (_nonempty_text(value.get("work_package_id"))
            and isinstance(value.get("time_window"), str) and value.get("time_window") in {"0-30 days", "31-90 days", "91-180 days"}
            and isinstance(value.get("related_finding_ids"), list)
            and _nonempty_text(value.get("objective"))
            and isinstance(value.get("ordered_implementation_steps"), list)
            and isinstance(value.get("dependencies"), list))
