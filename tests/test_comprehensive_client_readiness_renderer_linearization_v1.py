from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from typing import Any

from nico import comprehensive_client_readiness_v59 as readiness
from nico import comprehensive_report_truth_stabilization_v52 as legacy_truth


def _legacy_repair_symbols(text: str, symbols: set[str], coverage: int) -> str:
    """Frozen pre-linearization behavior used only for exact-output regression."""

    repaired = legacy_truth._repair_text(text)
    for broken, canonical in readiness._KNOWN_IDENTIFIER_REPAIRS.items():
        repaired = re.sub(
            re.escape(broken),
            canonical,
            repaired,
            flags=re.IGNORECASE,
        )
    for symbol in sorted(symbols, key=len, reverse=True):
        pattern = (
            r"(?<![A-Za-z0-9_])"
            + r"\s*".join(map(re.escape, symbol))
            + r"(?![A-Za-z0-9_])"
        )
        repaired = re.sub(pattern, symbol, repaired, flags=re.IGNORECASE)
    repaired = re.sub(
        r"\bS\s+p\s+ecific correction\b",
        "Specific correction",
        repaired,
    )
    repaired = readiness._COVERAGE_TEXT_RE.sub(
        lambda match: (
            f"{match.group('label')}{match.group('join')}{coverage}"
            f"{match.group('pct') or ''}"
        ),
        repaired,
    )
    return readiness._COVERAGE_PREFIX_RE.sub(
        lambda match: f"{coverage}{match.group('pct')}{match.group('tail')}",
        repaired,
    )


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_symbol_repair_plan_matches_legacy_for_exact_edge_cases() -> None:
    symbols = {
        "apply_scanner_artifact_scoring",
        "_spanish_pdf",
        "identifier",
        "identifier_extended",
        "kelvin",
        "specific",
    }
    plan = readiness._compile_symbol_repair_plan(symbols)
    values = (
        "APPLY_SCANNER_ARTIFACT_SCORING",
        "Refactor a p p l y _ s c a n n e r _ a r t i f a c t _ s c o r i n g now.",
        "Refactor `appy_ l scanner_artifact_scoring` and ` span ish_pdf`.",
        "identifier IDENTIFIER I D E N T I F I E R identifier_extended",
        "Do not alter identifier_extendedSuffix or Prefixidentifier.",
        "Dotless Unicode probe: IDENT\u0130F\u0130ER and \u0131dentifier.",
        "IGNORECASE Unicode probes: \u212aelvin and \u017fpecific.",
        "Analyzer execution coverage is 78%; 78% scanner execution completion.",
        "S p ecific correction",
        "no_whitespace_or_identifier_match",
    )

    for value in values:
        assert readiness._repair_symbols(
            value,
            symbols,
            100,
            symbol_repair_plan=plan,
        ) == _legacy_repair_symbols(value, symbols, 100)


def test_symbol_repair_plan_skips_regex_for_probe_miss() -> None:
    class CountingPattern:
        def __init__(self, delegate: re.Pattern[str]) -> None:
            self.delegate = delegate
            self.calls = 0

        def sub(self, replacement: str, value: str) -> str:
            self.calls += 1
            return self.delegate.sub(replacement, value)

    pattern = CountingPattern(
        re.compile(
            r"(?<![A-Za-z0-9_])u\s*n\s*r\s*e\s*l\s*a\s*t\s*e\s*d"
            r"\s*_\s*s\s*y\s*m\s*b\s*o\s*l(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
    )
    symbols = {"unrelated_symbol"}
    plan = (("unrelated_symbol", pattern, "unrelated_symbol"),)

    for value in (
        "candidate_0001",
        "0f4df13c22a979dd2f888f458c33d684a3fcbd29",
        "ordinary client evidence with whitespace",
    ):
        assert readiness._repair_symbols(
            value,
            symbols,
            0,
            symbol_repair_plan=plan,
        ) == _legacy_repair_symbols(value, symbols, 0)
    assert pattern.calls == 0

    matching_value = "Repair u n r e l a t e d _ s y m b o l exactly."
    assert readiness._repair_symbols(
        matching_value,
        symbols,
        0,
        symbol_repair_plan=plan,
    ) == _legacy_repair_symbols(matching_value, symbols, 0)
    assert pattern.calls == 1


def test_large_candidate_tree_is_digest_equivalent_and_compiles_once(
    monkeypatch: Any,
) -> None:
    candidate_count = 922
    evidence_cells_per_candidate = 288
    symbols = {f"symbol_{index:02d}_handler" for index in range(47)}
    evidence_payload = "retained immutable evidence / exact-source.json"
    candidates: list[dict[str, Any]] = []
    expected_candidates: list[dict[str, Any]] = []
    ordered_symbols = sorted(symbols)
    for index in range(candidate_count):
        symbol = ordered_symbols[index % len(ordered_symbols)]
        recommendation = (
            "Repair " + " ".join(symbol.upper()) + " without changing evidence."
            if index % 2
            else f"Repair {symbol.upper()} without changing evidence."
        )
        candidate = {
            "candidate_id": f"candidate_{index:04d}",
            "symbol": symbol,
            "recommendation": recommendation,
            "raw_payload": evidence_payload,
            "cluster_candidate_ids": [
                f"evidence_{index:04d}_{cell:03d}_immutable_exact_source_location"
                for cell in range(evidence_cells_per_candidate)
            ],
        }
        candidates.append(candidate)
        expected = dict(candidate)
        expected["recommendation"] = _legacy_repair_symbols(
            recommendation,
            symbols,
            0,
        )
        expected_candidates.append(expected)

    canonical = {"canonical_scanner_finding_register": {"findings": candidates}}
    expected = {
        "canonical_scanner_finding_register": {"findings": expected_candidates}
    }
    encoded_size = len(
        json.dumps(canonical, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
    assert 14_000_000 <= encoded_size <= 16_000_000
    assert _legacy_repair_symbols(evidence_payload, symbols, 0) == evidence_payload
    assert candidate_count * evidence_cells_per_candidate >= 250_000

    compile_calls = 0
    original_compile = readiness._compile_symbol_repair_plan

    def counted_compile(value: set[str]) -> readiness._SymbolRepairPlan:
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(value)

    monkeypatch.setattr(readiness, "_compile_symbol_repair_plan", counted_compile)
    started = time.perf_counter()
    output = readiness._normalize_tree(
        canonical,
        truth={},
        completed=set(),
        incomplete=set(),
        requested=0,
        symbols=symbols,
        technical_score=None,
    )
    elapsed = time.perf_counter() - started

    assert compile_calls == 1
    assert _digest(output) == _digest(expected)
    # This is a deliberately loose runaway guard; deterministic plan/substitution
    # call assertions above carry the algorithmic regression contract.
    assert elapsed < 60.0
