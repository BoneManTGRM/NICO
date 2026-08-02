from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive_maturity_label_truth.v1"

_LABEL_FIELDS = frozenset(
    {
        "maturity_label",
        "maturity_level",
        "maturity_rating",
        "maturity_tier",
    }
)
_HEAVY_FIELDS = frozenset({"pdf_base64", "markdown", "html", "report_package"})
_EXPLICIT_TEXT_PATTERNS = (
    re.compile(
        r"(?P<prefix>\bmaturity_(?:level|label|rating|tier)\s*[:=]\s*)"
        r"(?P<value>[^\n,;|}\]]+)",
        re.I,
    ),
    re.compile(
        r"(?P<prefix>\bmaturity\s+(?:level|label|rating|tier)\s*[:=]\s*)"
        r"(?P<value>[^\n,;|}\]]+)",
        re.I,
    ),
)


def _text(value: Any, limit: int = 240) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _candidate_label(value: Any) -> str:
    label = _text(value, 100)
    if not label:
        return ""
    if label.casefold() in {"unknown", "unavailable", "not assessed", "none", "n/a"}:
        return ""
    return label


def _contract_label(node: Any, *, depth: int = 0) -> str:
    if depth > 9:
        return ""
    if isinstance(node, Mapping):
        contract = node.get("client_readiness_contract")
        if isinstance(contract, Mapping):
            label = _candidate_label(contract.get("maturity_label"))
            if label:
                return label
        for key, value in node.items():
            if str(key).casefold() in _HEAVY_FIELDS:
                continue
            label = _contract_label(value, depth=depth + 1)
            if label:
                return label
    elif isinstance(node, (list, tuple)):
        for value in node:
            label = _contract_label(value, depth=depth + 1)
            if label:
                return label
    return ""


def _assessment_label(stages: Mapping[str, Any]) -> str:
    scoring = _mapping(stages.get("evidence_reconciliation_and_scoring"))
    assessment = _mapping(scoring.get("assessment"))
    for field in _LABEL_FIELDS:
        label = _candidate_label(assessment.get(field))
        if label:
            return label
    maturity = _mapping(assessment.get("maturity_signal"))
    for field in ("maturity_label", "maturity_level", "level", "label"):
        label = _candidate_label(maturity.get(field))
        if label:
            return label
    return ""


def derive_canonical_maturity_label(stages: Mapping[str, Any]) -> tuple[str, str]:
    """Return the report's authoritative maturity label and its source.

    The client-readiness contract is the final report taxonomy and outranks older stage
    aliases such as ``maturity_level: Senior``. Assessment maturity fields are used only
    when the contract does not expose a label.
    """

    scoring = _mapping(stages.get("evidence_reconciliation_and_scoring"))
    direct_contract = _mapping(scoring.get("client_readiness_contract"))
    label = _candidate_label(direct_contract.get("maturity_label"))
    if label:
        return label, "scoring.client_readiness_contract.maturity_label"

    assessment = _mapping(scoring.get("assessment"))
    assessment_contract = _mapping(assessment.get("client_readiness_contract"))
    label = _candidate_label(assessment_contract.get("maturity_label"))
    if label:
        return label, "scoring.assessment.client_readiness_contract.maturity_label"

    label = _contract_label(stages)
    if label:
        return label, "nested.client_readiness_contract.maturity_label"

    label = _assessment_label(stages)
    if label:
        return label, "scoring.assessment.maturity_signal"
    return "", "unavailable"


def _maturity_context(path: str) -> bool:
    lowered = path.casefold()
    return "maturity_signal" in lowered or ".maturity" in lowered or lowered.endswith("maturity")


def _replace_text(
    value: str,
    *,
    canonical_label: str,
    path: str,
    replacements: list[dict[str, str]],
) -> str:
    output = value
    for pattern in _EXPLICIT_TEXT_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            observed = _text(match.group("value"), 100)
            if observed.casefold() == canonical_label.casefold():
                return match.group(0)
            replacements.append(
                {
                    "path": path,
                    "observed": observed,
                    "canonical": canonical_label,
                    "kind": "explicit_text_alias",
                }
            )
            return f"{match.group('prefix')}{canonical_label}"

        output = pattern.sub(replace, output)
    return output


def _synchronize_node(
    node: Any,
    *,
    canonical_label: str,
    path: str,
    replacements: list[dict[str, str]],
) -> Any:
    if isinstance(node, str):
        return _replace_text(
            node,
            canonical_label=canonical_label,
            path=path,
            replacements=replacements,
        )
    if isinstance(node, list):
        return [
            _synchronize_node(
                value,
                canonical_label=canonical_label,
                path=f"{path}[{index}]",
                replacements=replacements,
            )
            for index, value in enumerate(node)
        ]
    if isinstance(node, tuple):
        return tuple(
            _synchronize_node(
                value,
                canonical_label=canonical_label,
                path=f"{path}[{index}]",
                replacements=replacements,
            )
            for index, value in enumerate(node)
        )
    if not isinstance(node, Mapping):
        return deepcopy(node)

    output: dict[str, Any] = {}
    for raw_key, raw_value in node.items():
        key = str(raw_key)
        lowered = key.casefold()
        current_path = f"{path}.{key}" if path else key
        if lowered in _HEAVY_FIELDS:
            output[key] = raw_value
            continue

        is_label_field = lowered in _LABEL_FIELDS
        is_nested_maturity_label = lowered in {"level", "label"} and _maturity_context(path)
        if is_label_field or is_nested_maturity_label:
            observed = _candidate_label(raw_value)
            if observed and observed.casefold() != canonical_label.casefold():
                replacements.append(
                    {
                        "path": current_path,
                        "observed": observed,
                        "canonical": canonical_label,
                        "kind": "structured_alias",
                    }
                )
            output[key] = canonical_label
            continue

        output[key] = _synchronize_node(
            raw_value,
            canonical_label=canonical_label,
            path=current_path,
            replacements=replacements,
        )
    return output


def synchronize_maturity_label_truth(
    stage_results: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project one canonical maturity taxonomy before report evidence is flattened.

    Only explicit maturity fields and explicit maturity-label text aliases are changed.
    Unrelated values such as role seniority remain untouched. The source mapping is not
    mutated, and report artifacts are not traversed.
    """

    canonical_label, source = derive_canonical_maturity_label(stage_results)
    if not canonical_label:
        return deepcopy(dict(stage_results)), {
            "status": "not_applied",
            "version": VERSION,
            "reason": "canonical_maturity_label_unavailable",
            "canonical_label": "",
            "canonical_source": source,
            "replacement_count": 0,
            "replacements": [],
            "source_stage_results_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    replacements: list[dict[str, str]] = []
    synchronized = _synchronize_node(
        stage_results,
        canonical_label=canonical_label,
        path="prior_stage_results",
        replacements=replacements,
    )
    if not isinstance(synchronized, dict):
        raise TypeError("synchronized_maturity_stage_results_must_be_mapping")
    return synchronized, {
        "status": "applied",
        "version": VERSION,
        "canonical_label": canonical_label,
        "canonical_source": source,
        "replacement_count": len(replacements),
        "replacements": replacements[:100],
        "explicit_maturity_aliases_only": True,
        "unrelated_seniority_preserved": True,
        "source_stage_results_mutated": False,
        "report_artifacts_traversed": False,
        "scores_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "derive_canonical_maturity_label",
    "synchronize_maturity_label_truth",
]
