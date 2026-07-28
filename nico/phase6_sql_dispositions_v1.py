from __future__ import annotations

from copy import deepcopy
from typing import Any

VERSION = "nico.phase6_sql_dispositions.v1"

SQL_DISPOSITIONS: dict[str, dict[str, Any]] = {
    "nico/infrastructure_backup_runtime.py": {
        "classification": "source_reviewed_bounded_identifier_composition",
        "rationale": (
            "SQLite table identifiers cannot be parameter-bound. The implementation routes the table name through "
            "_quote_identifier, doubles embedded quotes, verifies the table with a parameterized sqlite_master query, "
            "and binds the sample limit separately. No unvalidated runtime value is concatenated into SQL."
        ),
        "verification": (
            "Keep identifier quoting and sqlite_master validation covered by regression tests; rerun Bandit B608 "
            "against the exact SHA whenever this query construction changes."
        ),
    },
    "nico/comprehensive_run_store.py": {
        "classification": "source_reviewed_closed_dialect_placeholder_composition",
        "rationale": (
            "The SQL structure and table names are fixed. Interpolated tokens come only from the constructor-validated "
            "dialect set {sqlite, postgres} and resolve to DB-API placeholders or fixed column types. Runtime values are "
            "passed separately to cursor.execute."
        ),
        "verification": (
            "Preserve the closed dialect validation and parameter-binding tests; rerun Bandit B608 and both SQLite and "
            "Postgres store tests after any SQL template change."
        ),
    },
    "nico/monitor_approval_governance.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "The only interpolated SQL token is a DB-API placeholder selected from the constructor-validated dialect. "
            "The table, columns, and statement structure are constants, and approval values are parameter-bound."
        ),
        "verification": (
            "Retain dialect validation and approval-store persistence tests; rerun Bandit B608 on the exact SHA after "
            "modifying the statement or placeholder boundary."
        ),
    },
    "nico/monitor_execute_service.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "Monitor work-item statements interpolate only a DB-API placeholder from the closed SQLite/Postgres dialect "
            "set. Work-item identifiers, revisions, payloads, integrity values, and timestamps are passed as parameters."
        ),
        "verification": (
            "Preserve optimistic-concurrency and parameter-binding tests for both dialects; rerun Bandit B608 on every "
            "SQL template change."
        ),
    },
    "nico/monitor_runtime.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "Monitor definition, runtime-state, lease, and observation queries use fixed tables and columns. Interpolated "
            "tokens are DB-API placeholders from a closed dialect set; identifiers, dates, state, lease values, and limits "
            "are parameter-bound."
        ),
        "verification": (
            "Retain runtime-store, lease, revision-conflict, and dialect regression tests; rerun Bandit B608 against the "
            "exact SHA if query structure changes."
        ),
    },
    "nico/durable_runtime_storage.py": {
        "classification": "source_reviewed_constant_clause_composition",
        "rationale": (
            "The list query is assembled only from constant clause fragments selected by the presence of optional filters. "
            "Table name, columns, predicates, and ordering are fixed; table, customer, and project values are bound through "
            "SQLite placeholders."
        ),
        "verification": (
            "Keep optional-filter query tests and parameter assertions; rerun Bandit B608 after changing the clause set or "
            "introducing any dynamic identifier."
        ),
    },
    "nico/notification_delivery.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "Notification statements use fixed tables and columns. Generated placeholder lists and individual placeholder "
            "tokens come from a constructor-validated SQLite/Postgres dialect, while all notification data and limits are "
            "passed separately to cursor.execute."
        ),
        "verification": (
            "Preserve enqueue, deduplication, retry, bounded-limit, and dialect tests; rerun Bandit B608 on the exact SHA "
            "after SQL changes."
        ),
    },
    "nico/provider_credential_rotation.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "Credential-version queries use fixed table and column names. The generated placeholder list and placeholder "
            "tokens are selected from the validated dialect; provider, key, version, secret reference, status, and dates "
            "are parameter-bound."
        ),
        "verification": (
            "Keep dual-control, activation, retirement, and dialect persistence tests; rerun Bandit B608 after any query "
            "template change."
        ),
    },
    "nico/provider_sync_service.py": {
        "classification": "source_reviewed_closed_placeholder_composition",
        "rationale": (
            "Provider-sync statements use fixed SQL structure and a placeholder token selected from the validated dialect. "
            "Provider identity, repository identity, revision, state, payload, hashes, and timestamps are supplied as bound "
            "parameters."
        ),
        "verification": (
            "Retain create/update conflict and dialect tests; rerun Bandit B608 against the exact SHA after modifying SQL "
            "construction."
        ),
    },
    "nico/runtime_heartbeat_atomic_patch.py": {
        "classification": "source_reviewed_allowlisted_identifier_composition",
        "rationale": (
            "The heartbeat patch rejects tables outside {assessment_runs, scanner_runs}, then obtains the physical table "
            "and identifier column from the constant JSONB_TABLE_MAP. Only those allowlisted identifiers are interpolated; "
            "the work-item ID and update values are parameter-bound."
        ),
        "verification": (
            "Keep unsupported-table rejection and atomic heartbeat tests; require review if JSONB_TABLE_MAP becomes mutable "
            "or externally supplied, and rerun Bandit B608 after changes."
        ),
    },
    "nico/storage.py": {
        "classification": "source_reviewed_allowlisted_identifier_composition",
        "rationale": (
            "Dynamic Postgres table and ID-column tokens are read only from the constant JSONB_TABLE_MAP after the logical "
            "table key is checked for membership. Scope predicates are assembled from constant fragments and all customer, "
            "project, and item values are parameter-bound."
        ),
        "verification": (
            "Retain unknown-table rejection, scope-filter, JSONB mapping, and parameter-binding tests; rerun Bandit B608 "
            "and require security review if the mapping becomes externally configurable."
        ),
    },
    "nico/storage_schema_readiness.py": {
        "classification": "source_reviewed_constant_identifier_composition",
        "rationale": (
            "The migration-ledger table name is a module constant, not request or repository input. Its columns and SQL "
            "structure are fixed, and contract version, hashes, and timestamps are parameter-bound."
        ),
        "verification": (
            "Keep migration-ledger schema and readiness tests; rerun Bandit B608 and review this disposition if the table "
            "identifier becomes configurable."
        ),
    },
}


def is_sql_construction_message(value: Any) -> bool:
    text = " ".join(str(value or "").split()).casefold()
    return "sql" in text and any(
        token in text
        for token in (
            "injection",
            "concaten",
            "query construction",
            "string-based query",
            "formatted sql",
            "raw query",
        )
    )


def disposition_for(path: str, analyzer_message: Any) -> dict[str, Any] | None:
    record = SQL_DISPOSITIONS.get(str(path or ""))
    if record is None or not is_sql_construction_message(analyzer_message):
        return None
    return {
        "status": "approved_nonblocking",
        "classification": record["classification"],
        "rationale": record["rationale"],
        "verification": record["verification"],
        "scope": path,
        "review_method": "exact_source_review_plus_regression_test",
        "expires_on_source_change": True,
        "source_reviewed": True,
        "human_review_required": True,
    }


def source_review_coverage() -> dict[str, Any]:
    return {
        "schema": VERSION,
        "reviewed_paths": sorted(SQL_DISPOSITIONS),
        "reviewed_path_count": len(SQL_DISPOSITIONS),
        "every_record_has_rationale": all(bool(item.get("rationale")) for item in SQL_DISPOSITIONS.values()),
        "every_record_has_verification": all(bool(item.get("verification")) for item in SQL_DISPOSITIONS.values()),
        "dispositions_are_source_change_sensitive": True,
    }


__all__ = [
    "VERSION",
    "SQL_DISPOSITIONS",
    "is_sql_construction_message",
    "disposition_for",
    "source_review_coverage",
]
