from __future__ import annotations

import base64
import gzip
import hashlib
import json
from collections import defaultdict, deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

VERSION = "nico.candidate-lineage-migration.v1"
_BASELINE_FILE = Path(__file__).resolve().parents[1] / "evidence" / "candidate-lineage" / "baseline-9c876ba4.json.gz.b64"
_ROOTS = (".github/", "apps/", "config/", "docs/", "evidence/", "nico/", "scripts/", "tests/")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _path(value: Any) -> str:
    path = str(value or "").replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    lower = path.casefold()
    marker = "/repo/"
    if marker in lower:
        path = path[lower.rfind(marker) + len(marker):]
        lower = path.casefold()
    indexes = [lower.rfind(root) for root in _ROOTS if lower.rfind(root) >= 0]
    return path[max(indexes):] if indexes else path


def _hash(parts: list[Any]) -> str:
    payload = "\x1f".join(_norm(value) for value in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def lineage_keys(record: Mapping[str, Any]) -> dict[str, Any]:
    category = _norm(record.get("category"))
    scanner = _norm(record.get("scanner") or record.get("tool")).replace("_", "-")
    rule = _norm(record.get("rule_id") or record.get("rule"))
    source_path = _path(record.get("source_path") or record.get("path") or record.get("location"))
    line = int(record.get("line") or 0)
    title = _norm(record.get("evidence") or record.get("title") or record.get("message"))
    return {
        "exact": _hash([category, scanner, rule, source_path, line]),
        "semantic": _hash([category, scanner, rule, source_path, title]),
        "group": _hash([category, scanner, rule, source_path]),
        "line": line,
        "path": source_path,
    }


def load_default_baseline(path: Path | None = None) -> dict[str, Any]:
    source = path or _BASELINE_FILE
    encoded = "".join(source.read_text(encoding="utf-8").split())
    decoded = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
    baseline = json.loads(decoded)
    if baseline.get("s") != "nico.candidate-lineage-baseline.v2":
        raise ValueError("candidate_lineage_baseline_schema_invalid")
    records = baseline.get("x")
    if not isinstance(records, list) or len(records) != int(baseline.get("n") or -1):
        raise ValueError("candidate_lineage_baseline_count_invalid")
    if baseline.get("a") != "none":
        raise ValueError("candidate_lineage_baseline_approval_authority_invalid")
    return baseline


def _baseline_rows(baseline: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in baseline.get("x") or []:
        if not isinstance(raw, list) or len(raw) != 7:
            raise ValueError("candidate_lineage_baseline_record_invalid")
        exact, semantic, group, line, candidate, proposal, cluster = raw
        rows.append({
            "exact": str(exact),
            "semantic": str(semantic),
            "group": str(group),
            "line": int(line or 0),
            "candidate_id": str(candidate),
            "proposed_disposition": str(proposal),
            "cluster_id": str(cluster),
        })
    return rows


def _index(rows: list[dict[str, Any]], field: str) -> dict[str, deque[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return {
        key: deque(sorted(values, key=lambda item: (item["line"], item["candidate_id"])))
        for key, values in grouped.items()
    }


def _take_nearest(queue: deque[dict[str, Any]], line: int) -> dict[str, Any] | None:
    if not queue:
        return None
    values = list(queue)
    selected = min(values, key=lambda item: (abs(item["line"] - line), item["line"], item["candidate_id"]))
    queue.remove(selected)
    return selected


def apply_candidate_lineage(
    register: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output = deepcopy(dict(register))
    current = [deepcopy(item) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    try:
        source = dict(baseline or load_default_baseline())
        prior = _baseline_rows(source)
    except Exception as exc:
        output["candidate_lineage"] = {
            "artifact_schema": VERSION,
            "status": "unavailable",
            "reason": type(exc).__name__,
            "prior_register_available": False,
            "human_approval_carried_forward": False,
            "client_delivery_allowed": False,
        }
        return output

    exact = _index(prior, "exact")
    semantic = _index(prior, "semantic")
    group = _index(prior, "group")
    consumed: set[str] = set()
    counts = defaultdict(int)

    def take(index: dict[str, deque[dict[str, Any]]], key: str, line: int) -> dict[str, Any] | None:
        queue = index.get(key)
        while queue:
            candidate = _take_nearest(queue, line)
            if candidate and candidate["candidate_id"] not in consumed:
                consumed.add(candidate["candidate_id"])
                return candidate
        return None

    for record in current:
        keys = lineage_keys(record)
        prior_row = take(exact, keys["exact"], keys["line"])
        status = "carried_forward_exact"
        if prior_row is None:
            prior_row = take(semantic, keys["semantic"], keys["line"])
            status = "carried_forward_location_changed"
        if prior_row is None:
            prior_row = take(group, keys["group"], keys["line"])
            status = "carried_forward_evidence_changed"
        record["candidate_id"] = record.get("candidate_id") or record.get("finding_id")
        record["lineage_id"] = f"NICO-LINEAGE-{keys['group'].upper()}-{keys['exact'][:8].upper()}"
        record["lineage_status"] = status if prior_row else "newly_observed"
        record["human_approval_status"] = "pending"
        record["human_approval_carried_forward"] = False
        if prior_row:
            record["prior_candidate_id"] = prior_row["candidate_id"]
            record["prior_target_commit_sha"] = source.get("c")
            record["prior_proposed_disposition"] = prior_row["proposed_disposition"]
            record["prior_cluster_id"] = prior_row["cluster_id"]
            record["proposed_disposition"] = prior_row["proposed_disposition"]
            counts[status] += int(record.get("occurrence_count") or 1)
        else:
            counts["newly_observed"] += int(record.get("occurrence_count") or 1)

    tombstones = [
        {
            "prior_candidate_id": row["candidate_id"],
            "prior_target_commit_sha": source.get("c"),
            "prior_proposed_disposition": row["proposed_disposition"],
            "prior_cluster_id": row["cluster_id"],
            "lineage_status": "no_longer_observed",
            "human_approval_carried_forward": False,
        }
        for row in prior
        if row["candidate_id"] not in consumed
    ]
    counts["no_longer_observed"] = len(tombstones)
    output["findings"] = current
    output["candidate_lineage"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "prior_register_available": True,
        "prior_register_schema": source.get("s"),
        "prior_target_commit_sha": source.get("c"),
        "prior_candidate_count": int(source.get("n") or 0),
        "current_candidate_count": int((output.get("totals") or {}).get("raw") or 0),
        "carried_forward_exact": counts["carried_forward_exact"],
        "carried_forward_location_changed": counts["carried_forward_location_changed"],
        "carried_forward_evidence_changed": counts["carried_forward_evidence_changed"],
        "carried_forward_total": (
            counts["carried_forward_exact"]
            + counts["carried_forward_location_changed"]
            + counts["carried_forward_evidence_changed"]
        ),
        "newly_observed": counts["newly_observed"],
        "no_longer_observed": counts["no_longer_observed"],
        "tombstones": tombstones,
        "proposed_dispositions_carried_forward": True,
        "human_approval_carried_forward": False,
        "disposition_authority": "proposal_only_pending_authorized_human_review",
        "score_effect": "review_required_candidates_remain_assurance_only",
        "client_delivery_allowed": False,
    }
    output["canonical_digest_sha256"] = hashlib.sha256(
        json.dumps(current, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return output


__all__ = [
    "VERSION",
    "apply_candidate_lineage",
    "lineage_keys",
    "load_default_baseline",
]
