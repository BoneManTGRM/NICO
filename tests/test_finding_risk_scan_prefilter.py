from __future__ import annotations

import random
import re
from copy import deepcopy
from types import SimpleNamespace

import pytest

from nico import client_finding_remediation_register_v1 as register


SHA = "a" * 40
_LEGACY_RISK = re.compile(
    r"(?P<path>[A-Za-z0-9_@./+\-]+\.(?:py|js|jsx|ts|tsx|java|go|rb|rs|cs|php|swift|kt|kts))"
    r":(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<rule>[A-Za-z0-9_.\-]+)\s*[—-]\s*(?P<message>.+)",
    re.IGNORECASE,
)
_LEGACY_HOTSPOT = re.compile(
    r"(?:Actionable\s+hotspot\s+)?(?P<path>[A-Za-z0-9_@./+\-]+\.(?:py|js|jsx|ts|tsx))"
    r":(?P<line>\d+)\s*[·-]\s*(?P<symbol>[^·]+?)\s*[·-]\s*complexity\s+(?P<complexity>\d+)",
    re.IGNORECASE,
)


def _matches(pattern, raw):
    return _match_values(pattern.finditer(raw))


def _match_values(matches):
    return [(match.span(), match.groups(), match.groupdict(), match.regs) for match in matches]


def _legacy_records(canonical, monkeypatch):
    # Independent copies of both original expressions drive the same record
    # assembly, with candidate scanning and the literal guard disabled.
    with monkeypatch.context() as patch:
        patch.setattr(register, "_RISK_LINE", _LEGACY_RISK)
        patch.setattr(register, "_HOTSPOT_LINE", _LEGACY_HOTSPOT)
        patch.setattr(register, "_line_matches", lambda raw, pattern, starts: pattern.finditer(raw))
        patch.setattr(register, "_HOTSPOT_REQUIRED", SimpleNamespace(search=lambda raw: True))
        return register._risk_string_records(canonical, SHA)


def _assert_record_parity(canonical, monkeypatch):
    before = deepcopy(canonical)
    expected = _legacy_records(canonical, monkeypatch)
    actual = register._risk_string_records(canonical, SHA)
    assert actual == expected
    assert canonical == before
    return actual


@pytest.mark.parametrize("raw", [
    "",
    "a" * 128,
    "src/plain.py:1: python_eval_exec — Review execution.",
    "src/missing.py:1 · name · no measurement",
    "src/incomplete.py:2 · name · complexity",
    "complexity appears but there is no source anchor",
    "Actionable hotspot src/main.py:12 · dispatch · complexity 37",
    "prefix src/entry.tsx:9 - Component - COMPLEXITY 29 suffix",
    "src/one.js:4 · first · complexity 10\nsrc/two.py:8 · second · complexity 20",
    "src/main.py:12 · line one\nline two · complexity 37",
    "src/main.py:12 - symbol-with-hyphens - complexity 37",
    "src/main.py:12 · dispatch · CoMpLeXiTy\t37",
    "src/main.py:12 · dispatch · COMPLEXİTY 37",
    "src/main.py:12 · dispatch · COMPLEXıTY 37",
    "src/maİn.py:12 · dispatch · complexity 37",
    "src/main.py:١٢ · dispatch · complexity ٣٧",
    "tests/example.py:2 · sample · complexity 40",
])
def test_prefilter_preserves_exact_hotspot_spans_and_groups(raw):
    assert register._HOTSPOT_LINE.pattern == _LEGACY_HOTSPOT.pattern
    assert register._HOTSPOT_LINE.flags == _LEGACY_HOTSPOT.flags
    guarded = _match_values(register._line_matches(raw, register._HOTSPOT_LINE, register._HOTSPOT_LINE_START)) if register._HOTSPOT_REQUIRED.search(raw) else []
    assert guarded == _matches(_LEGACY_HOTSPOT, raw)


@pytest.mark.parametrize("word", ["complexity", "COMPLEXITY", "COMPLEXİTY", "COMPLEXıTY"])
def test_full_records_preserve_casefold_matches_multiline_symbols_and_order(word, monkeypatch):
    canonical = {
        "first": (
            f"src/first.py:8 · first\nsecond · {word} 32\n"
            "src/risk.py:3:4: python_eval_exec — Review execution.\n"
            f"src/last.ts:9 - dispatch - {word} 41"
        ),
        "last": "src/final.py:20: tls_verify_disabled — Restore TLS verification.",
    }
    actual = _assert_record_parity(canonical, monkeypatch)
    # The legacy parser emits risks first, then hotspots within each raw string.
    assert [(row["path"], row["category"]) for row in actual] == [
        ("src/risk.py", "security"),
        ("src/first.py", "architecture"),
        ("src/last.ts", "architecture"),
        ("src/final.py", "security"),
    ]
    assert actual[1]["symbol"] == "first second"
    assert all(row["exact_commit_sha"] == SHA and row["human_disposition_required"] for row in actual)


def test_aliases_remain_revisited_without_deduplication_or_input_mutation(monkeypatch):
    shared = [
        "src/shared.py:7 · shared · complexity 33",
        "src/command.py:8: python_os_system — Review command execution.",
    ]
    canonical = {"first": shared, "second": shared, "tuple": (shared[0],)}
    actual = _assert_record_parity(canonical, monkeypatch)
    assert [row["path"] for row in actual] == [
        "src/shared.py", "src/command.py", "src/shared.py", "src/command.py", "src/shared.py",
    ]
    assert canonical["first"] is canonical["second"] is shared


def test_source_observation_and_nonproduction_exclusions_stay_exact(monkeypatch):
    observation = {
        "path": "src/observed.py", "line": 10, "column": 3,
        "rule_id": "python_eval_exec", "semantic_class": "source_observation",
        "repository_revision": SHA, "revision_match": True,
    }
    excluded = dict(observation, path="src/excluded.py", line=20, column=None,
                    semantic_class="excluded_non_production_observation")
    wrong_revision = dict(observation, path="src/old.py", line=30, repository_revision="b" * 40)
    canonical = {
        "source_risk_observations": [observation, excluded, wrong_revision],
        "evidence": [
            "src/observed.py:10:3: python_eval_exec — Same exact observation.",
            "src/observed.py:10: python_eval_exec — No column observation.",
            "src/observed.py:10:4: python_eval_exec — Different column remains.",
            "src/excluded.py:20: python_eval_exec — Classified source observation.",
            "src/old.py:30:3: python_eval_exec — Different revision remains.",
            "tests/sample.py:1: python_eval_exec — Nonproduction risk.",
            "tests/sample.py:2 · sample · complexity 31",
            "src/observed.py:10 · observed · complexity 32",
            "src/production.py:40 · production · complexity 33",
        ],
    }
    actual = _assert_record_parity(canonical, monkeypatch)
    assert [(row["path"], row["column"], row["category"]) for row in actual] == [
        ("src/observed.py", 4, "security"),
        ("src/old.py", 3, "security"),
        ("src/observed.py", None, "architecture"),
        ("src/production.py", None, "architecture"),
    ]


def _nested(value, levels):
    for _ in range(levels):
        value = {"nested": value}
    return value


def test_skip_keys_and_depth_seven_eight_are_unchanged(monkeypatch):
    canonical = {
        "accepted": _nested("src/depth7.py:7 · depth_seven · complexity 31", 6),
        "too_deep": _nested("src/depth8.py:8 · depth_eight · complexity 32", 7),
        "visible": "src/visible.py:9: python_eval_exec — Visible risk.",
    }
    for key in register._SKIP_RECURSIVE_KEYS:
        canonical[key] = [
            "src/hidden.py:10 · hidden · complexity 33",
            "src/hidden.py:11: python_eval_exec — Hidden risk.",
        ]
    actual = _assert_record_parity(canonical, monkeypatch)
    assert [row["path"] for row in actual] == ["src/depth7.py", "src/visible.py"]


def test_absent_literal_skips_hotspot_matcher_but_keeps_risk_matcher(monkeypatch):
    original = register._line_matches
    risk_calls = []
    hotspot_calls = []

    def matches(raw, pattern, starts):
        (risk_calls if pattern is register._RISK_LINE else hotspot_calls).append(raw)
        return original(raw, pattern, starts)

    monkeypatch.setattr(register, "_line_matches", matches)
    values = ["a" * 128, "src/risk.py:4: python_eval_exec — Retain this finding."]
    actual = register._risk_string_records({"evidence": values}, SHA)
    assert risk_calls == values
    assert hotspot_calls == []
    assert [row["path"] for row in actual] == ["src/risk.py"]


def test_literal_presence_runs_hotspot_scanner_even_without_valid_match(monkeypatch):
    original = register._line_matches
    calls = []

    def matches(raw, pattern, starts):
        if pattern is register._HOTSPOT_LINE:
            calls.append(raw)
        return original(raw, pattern, starts)

    monkeypatch.setattr(register, "_line_matches", matches)
    raw = "A retained complexity explanation without a valid source anchor."
    assert register._risk_string_records({"evidence": raw}, SHA) == []
    assert calls == [raw]


@pytest.mark.parametrize("raw", [
    "xActionable hotspot src/first.py:1 · first · complexity 30",
    "Actionable hotspotActionable hotspot src/first.py:1 · first · complexity 30",
    "src/first.py:1 · first · complexity 30next.py:2 · next · complexity 31",
    "src/first.py:1 · first · complexity 30xActionable hotspot next.py:2 · next · complexity 31",
    "src/first.py:1 - src/second.py:2 - symbol - complexity 30",
    "src/first.py:1 · first · complexity 30.py:2 · empty_stem · complexity 31",
    "src/first.py:1 · first · complexity 30x.py:2 · second · complexity 31",
    "!İıſK.py:١٢:٣: python_eval_exec — first\n!Kİıſ.tſ:٤ · line\none · COMPLEXİTY ٣٧",
    "src/example.KT:2:3: some_rule - line one\nline two\nsrc/example.kts:4: rule- suffix",
    "bad.py:no · symbol · complexity 32\nvalid.py:2 · valid · complexity 33",
    "a" * 6000 + " complexity elsewhere\nvalid.py:3: rule — Retained risk.\n"
    "valid.py:4 · symbol · complexity 30next.py:5 · next · complexity 31",
    "a" * 6000 + ".py:invalid · symbol · complexity 20",
])
def test_candidate_scan_preserves_original_match_and_group_spans(raw):
    for original, pattern, starts in [
        (_LEGACY_RISK, register._RISK_LINE, register._RISK_LINE_START),
        (_LEGACY_HOTSPOT, register._HOTSPOT_LINE, register._HOTSPOT_LINE_START),
    ]:
        assert pattern.pattern == original.pattern
        assert pattern.flags == original.flags
        assert _match_values(register._line_matches(raw, pattern, starts)) == _matches(original, raw)


def test_failed_long_path_run_does_not_retry_each_character():
    raw = "a" * 30000 + " complexity elsewhere\nvalid.py:3 · symbol · complexity 30"
    for pattern, starts in [
        (register._RISK_LINE, register._RISK_LINE_START),
        (register._HOTSPOT_LINE, register._HOTSPOT_LINE_START),
    ]:
        calls = []

        def match(value, position):
            calls.append(position)
            return pattern.match(value, position)

        list(register._line_matches(raw, SimpleNamespace(match=match), starts))
        assert len(calls) < 10
        assert not any(0 < position < 30000 for position in calls)


def test_seeded_mixed_text_scan_parity_against_independent_original_regexes():
    rng = random.Random(9387)
    fragments = [
        "", "x", "a" * 120, ".py", "Actionable", "Actionable hotspot ",
        "!", " ", "\n", "\t", "\u2003", "·", "-", "—", "complexity 30", "٣٠",
        "src/a.py:1 · first · complexity 30", "src/b.tsx:2 - second - COMPLEXıTY 31",
        "ſrc/Kİı.py:١:٢: r_İſK — review", "src/c.java:4: rule - security message",
        "src/no.py:invalid · unsupported · complexity", "src/d.js:4 - a\nb - complexity 32",
    ]
    for _ in range(1500):
        raw = "".join(rng.choices(fragments, k=rng.randrange(1, 10)))
        for original, pattern, starts in [
            (_LEGACY_RISK, register._RISK_LINE, register._RISK_LINE_START),
            (_LEGACY_HOTSPOT, register._HOTSPOT_LINE, register._HOTSPOT_LINE_START),
        ]:
            assert _match_values(register._line_matches(raw, pattern, starts)) == _matches(original, raw), raw
