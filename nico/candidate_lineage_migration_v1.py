from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

VERSION = "nico.candidate-lineage-migration.v4"
_ROOT = Path(__file__).resolve().parents[1]
_BASELINE_DIR = _ROOT / "evidence" / "candidate-lineage" / "baseline-9c876ba4-chunks"
_BASELINE_MANIFEST = _BASELINE_DIR / "manifest.json"
_TRIAGE_MANIFEST = _ROOT / "evidence" / "triage-662" / "manifest.json"
_EXPECTED_REPOSITORY = "BoneManTGRM/NICO"
_EXPECTED_COMMIT = "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
_EXPECTED_COUNT = 662
_EXPECTED_COUNTS = {"dependency": 59, "secret": 17, "static": 586}
_EXPECTED_REGISTER_SHA256 = "8cba692c557a0503da37bdbadc77cfd57e687421fcf8d6044d98f781922182a2"
_EXPECTED_ENCODED_SHA256 = "97f8307f3a4ca4e37232637acc1877f69c603bd1484c984f868c61cdaacba509"
_EXPECTED_PROPOSALS = {"dependency": "dependency_reachability_and_upgrade_review", "secret": "test_fixture_confirmation_required", "static": "source_review_required"}
_ROOTS = (".github/", "apps/", "config/", "docs/", "evidence/", "nico/", "scripts/", "tests/")
_HEX20 = re.compile(r"^[0-9a-f]{20}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SUBJECT_FIELDS = ("repository", "project_id", "workspace_id", "assessment_target_id")


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


def _normalize_repository(value: Any) -> str:
    text = _text(value).replace("\\", "/").rstrip("/")
    lowered = text.casefold()
    for prefix in ("https://github.com/", "http://github.com/", "ssh://git@github.com/", "git@github.com:"):
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break
    if text.casefold().endswith(".git"):
        text = text[:-4]
    return text.casefold()


def subject_identity(value: Mapping[str, Any]) -> dict[str, str]:
    explicit = value.get("assessment_subject") if isinstance(value.get("assessment_subject"), Mapping) else {}
    aliases = {
        "repository": ("repository", "repository_full_name", "repo_full_name", "repository_name", "repo", "repository_url"),
        "project_id": ("project_id", "project_identity"),
        "workspace_id": ("workspace_id", "workspace_identity"),
        "assessment_target_id": ("assessment_target_id", "technical_target_identity", "target_id"),
    }
    output: dict[str, str] = {}
    for canonical, keys in aliases.items():
        raw: Any = None
        for source in (explicit, value):
            for key in keys:
                candidate = source.get(key) if isinstance(source, Mapping) else None
                if candidate not in (None, "", {}, []):
                    raw = candidate
                    break
            if raw is not None:
                break
        if isinstance(raw, Mapping):
            raw = raw.get("full_name") or raw.get("name") or raw.get("id") or raw.get("url")
        normalized = _normalize_repository(raw) if canonical == "repository" else _norm(raw)
        if normalized:
            output[canonical] = normalized
    return output


def _baseline_subject(source: Mapping[str, Any]) -> dict[str, str]:
    explicit = source.get("assessment_subject") if isinstance(source.get("assessment_subject"), Mapping) else {}
    value = {
        "assessment_subject": explicit,
        "repository": source.get("r") or source.get("repository"),
        "project_id": source.get("project_id") or source.get("p"),
        "workspace_id": source.get("workspace_id") or source.get("w"),
        "assessment_target_id": source.get("assessment_target_id") or source.get("t"),
    }
    return subject_identity(value)


def _subject_match(register: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[bool, dict[str, str], dict[str, str], str]:
    current = subject_identity(register)
    prior = _baseline_subject(source)
    if not current or "repository" not in current:
        return False, current, prior, "current_subject_identity_missing"
    if not prior or "repository" not in prior:
        return False, current, prior, "prior_subject_identity_missing"
    if current != prior:
        return False, current, prior, "assessment_subject_mismatch"
    return True, current, prior, "assessment_subject_exact_match"


def _json_object(path: Path, error: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(error) from exc
    if not isinstance(value, dict):
        raise ValueError(error)
    return value


def _counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    try:
        result = {str(key): int(raw) for key, raw in value.items()}
    except (TypeError, ValueError):
        return {}
    return result if all(number >= 0 for number in result.values()) else {}


def _validate_source_manifest() -> dict[str, Any]:
    source = _json_object(_TRIAGE_MANIFEST, "candidate_lineage_source_manifest_invalid")
    artifacts = source.get("artifacts") if isinstance(source.get("artifacts"), Mapping) else {}
    try:
        candidate_count = int(source.get("candidate_count") or -1)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_lineage_source_manifest_mismatch") from exc
    required = (
        source.get("schema") == "nico.triage_candidate_package_manifest.v1"
        and source.get("repository") == _EXPECTED_REPOSITORY
        and source.get("target_commit_sha") == _EXPECTED_COMMIT
        and candidate_count == _EXPECTED_COUNT
        and _counts(source.get("counts")) == _EXPECTED_COUNTS
        and source.get("automated_status") == "automated_draft"
        and source.get("human_review_status") == "pending"
        and source.get("client_delivery_status") == "blocked"
        and source.get("two_run_parity_verified") is True
        and artifacts.get("candidate-register.json") == _EXPECTED_REGISTER_SHA256
    )
    if not required:
        raise ValueError("candidate_lineage_source_manifest_mismatch")
    return source


def _validate_baseline(baseline: Mapping[str, Any], retained: bool) -> dict[str, Any]:
    value = dict(baseline)
    records = value.get("x")
    try:
        count = int(value.get("n"))
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_lineage_baseline_count_invalid") from exc
    if value.get("s") != "nico.candidate-lineage-baseline.v2":
        raise ValueError("candidate_lineage_baseline_schema_invalid")
    if not isinstance(records, list) or len(records) != count:
        raise ValueError("candidate_lineage_baseline_count_invalid")
    if value.get("a") != "none":
        raise ValueError("candidate_lineage_baseline_approval_authority_invalid")
    if retained:
        if value.get("r") != _EXPECTED_REPOSITORY or value.get("c") != _EXPECTED_COMMIT:
            raise ValueError("candidate_lineage_baseline_identity_invalid")
        if count != _EXPECTED_COUNT or _counts(value.get("k")) != _EXPECTED_COUNTS:
            raise ValueError("candidate_lineage_baseline_count_invalid")
        ids: set[str] = set()
        categories: Counter[str] = Counter()
        for raw in records:
            if not isinstance(raw, list) or len(raw) != 7:
                raise ValueError("candidate_lineage_baseline_record_invalid")
            exact, semantic, group, line, candidate, proposal, cluster = raw
            if not all(_HEX20.fullmatch(str(item)) for item in (exact, semantic, group)):
                raise ValueError("candidate_lineage_baseline_identity_hash_invalid")
            if not isinstance(line, int) or line < 0:
                raise ValueError("candidate_lineage_baseline_line_invalid")
            candidate = str(candidate)
            proposal = str(proposal)
            if not candidate or candidate in ids or not str(cluster):
                raise ValueError("candidate_lineage_baseline_record_identity_invalid")
            category = next((name for name in _EXPECTED_COUNTS if candidate.startswith(f"NICO-{name.upper()}-")), "")
            if not category or proposal != _EXPECTED_PROPOSALS[category]:
                raise ValueError("candidate_lineage_baseline_proposal_invalid")
            ids.add(candidate)
            categories[category] += 1
        if dict(categories) != _EXPECTED_COUNTS or len(ids) != _EXPECTED_COUNT:
            raise ValueError("candidate_lineage_baseline_category_counts_invalid")
    return value


def _load_retained_baseline() -> dict[str, Any]:
    source = _validate_source_manifest()
    manifest = _json_object(_BASELINE_MANIFEST, "candidate_lineage_baseline_manifest_invalid")
    if not (
        manifest.get("schema") == "nico.candidate-lineage-baseline-chunks.v1"
        and manifest.get("baseline_schema") == "nico.candidate-lineage-baseline.v2"
        and manifest.get("repository") == _EXPECTED_REPOSITORY
        and manifest.get("target_commit_sha") == _EXPECTED_COMMIT
        and int(manifest.get("candidate_count") or -1) == _EXPECTED_COUNT
        and _counts(manifest.get("counts")) == _EXPECTED_COUNTS
        and manifest.get("approval_authority") == "none"
        and manifest.get("source_candidate_register_sha256") == source["artifacts"]["candidate-register.json"]
        and manifest.get("encoded_sha256") == _EXPECTED_ENCODED_SHA256
    ):
        raise ValueError("candidate_lineage_baseline_manifest_mismatch")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("candidate_lineage_baseline_chunks_invalid")
    encoded_parts: list[str] = []
    for expected_index, meta in enumerate(chunks):
        if not isinstance(meta, Mapping) or int(meta.get("index", -1)) != expected_index:
            raise ValueError("candidate_lineage_baseline_chunk_metadata_invalid")
        filename = str(meta.get("file") or "")
        digest = str(meta.get("sha256") or "")
        if Path(filename).name != filename or not filename.endswith(".b64") or not _HEX64.fullmatch(digest):
            raise ValueError("candidate_lineage_baseline_chunk_metadata_invalid")
        encoded = "".join((_BASELINE_DIR / filename).read_text(encoding="ascii").split())
        if len(encoded) != int(meta.get("length")) or hashlib.sha256(encoded.encode("ascii")).hexdigest() != digest:
            raise ValueError("candidate_lineage_baseline_chunk_digest_invalid")
        encoded_parts.append(encoded)
    encoded = "".join(encoded_parts)
    if hashlib.sha256(encoded.encode("ascii")).hexdigest() != _EXPECTED_ENCODED_SHA256:
        raise ValueError("candidate_lineage_baseline_encoded_digest_invalid")
    try:
        compressed = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
        baseline = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        raise ValueError("candidate_lineage_baseline_payload_invalid") from exc
    if not isinstance(baseline, Mapping):
        raise ValueError("candidate_lineage_baseline_payload_invalid")
    return _validate_baseline(baseline, retained=True)


def load_default_baseline(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        return _load_retained_baseline()
    try:
        encoded = "".join(Path(path).read_text(encoding="utf-8").split())
        compressed = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
        baseline = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except (OSError, ValueError, binascii.Error, UnicodeError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        raise ValueError("candidate_lineage_legacy_baseline_invalid") from exc
    if not isinstance(baseline, Mapping):
        raise ValueError("candidate_lineage_legacy_baseline_invalid")
    return _validate_baseline(baseline, retained=False)


def _baseline_rows(baseline: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in baseline.get("x") or []:
        if not isinstance(raw, list) or len(raw) != 7:
            raise ValueError("candidate_lineage_baseline_record_invalid")
        exact, semantic, group, line, candidate, proposal, cluster = raw
        rows.append({"exact": str(exact), "semantic": str(semantic), "group": str(group), "line": int(line or 0), "candidate_id": str(candidate), "proposed_disposition": str(proposal), "cluster_id": str(cluster)})
    return rows


def _index(rows: list[dict[str, Any]], field: str) -> dict[str, deque[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return {key: deque(sorted(values, key=lambda item: (item["line"], item["candidate_id"]))) for key, values in grouped.items()}


def _take_nearest(queue: deque[dict[str, Any]], line: int) -> dict[str, Any] | None:
    if not queue:
        return None
    selected = min(list(queue), key=lambda item: (abs(item["line"] - line), item["line"], item["candidate_id"]))
    queue.remove(selected)
    return selected


def _count(record: Mapping[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count") or 1))
    except (TypeError, ValueError):
        return 1


def apply_candidate_lineage(register: Mapping[str, Any], *, baseline: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = deepcopy(dict(register))
    current = [deepcopy(dict(item)) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    try:
        source = dict(baseline or load_default_baseline())
        prior = _baseline_rows(source)
    except Exception as exc:
        output["candidate_lineage"] = {"artifact_schema": VERSION, "status": "unavailable", "reason": type(exc).__name__, "prior_register_available": False, "human_approval_carried_forward": False, "client_delivery_allowed": False}
        return output

    compatible, current_subject, prior_subject, subject_reason = _subject_match(output, source)
    exact = _index(prior, "exact") if compatible else {}
    semantic = _index(prior, "semantic") if compatible else {}
    group = _index(prior, "group") if compatible else {}
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
        record["evidence_changed"] = status == "carried_forward_evidence_changed" if prior_row else False
        record["human_approval_status"] = "pending"
        record["human_approval_carried_forward"] = False
        record["lineage_subject_match"] = compatible
        if prior_row:
            record["prior_candidate_id"] = prior_row["candidate_id"]
            record["previous_candidate_identity"] = prior_row["candidate_id"]
            record["prior_target_commit_sha"] = source.get("c")
            record["prior_proposed_disposition"] = prior_row["proposed_disposition"]
            record["prior_cluster_id"] = prior_row["cluster_id"]
            record["proposed_disposition"] = prior_row["proposed_disposition"]
            counts[status] += _count(record)
        else:
            counts["newly_observed"] += _count(record)

    tombstones = (
        [
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
        if compatible
        else []
    )
    counts["no_longer_observed"] = len(tombstones)
    output["findings"] = current
    output["candidate_lineage"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "prior_register_available": True,
        "prior_register_schema": source.get("s"),
        "prior_target_commit_sha": source.get("c"),
        "prior_candidate_count": int(source.get("n") or 0),
        "current_candidate_count": sum(_count(item) for item in current),
        "carried_forward_exact": counts["carried_forward_exact"],
        "carried_forward_location_changed": counts["carried_forward_location_changed"],
        "carried_forward_evidence_changed": counts["carried_forward_evidence_changed"],
        "carried_forward_total": counts["carried_forward_exact"] + counts["carried_forward_location_changed"] + counts["carried_forward_evidence_changed"],
        "newly_observed": counts["newly_observed"],
        "no_longer_observed": counts["no_longer_observed"],
        "tombstones": tombstones,
        "prior_candidates_not_compared_due_subject_mismatch": int(source.get("n") or 0) if not compatible else 0,
        "assessment_subject_match": compatible,
        "assessment_subject_match_reason": subject_reason,
        "current_assessment_subject": current_subject,
        "prior_assessment_subject": prior_subject,
        "cross_repository_carry_forward_allowed": False,
        "cross_project_carry_forward_allowed": False,
        "cross_workspace_carry_forward_allowed": False,
        "cross_target_carry_forward_allowed": False,
        "proposed_dispositions_carried_forward": compatible,
        "human_approval_carried_forward": False,
        "disposition_authority": "proposal_only_pending_authorized_human_review",
        "score_effect": "review_required_candidates_remain_assurance_only",
        "client_delivery_allowed": False,
    }
    output["canonical_digest_sha256"] = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return output


__all__ = ["VERSION", "apply_candidate_lineage", "lineage_keys", "load_default_baseline", "subject_identity"]
