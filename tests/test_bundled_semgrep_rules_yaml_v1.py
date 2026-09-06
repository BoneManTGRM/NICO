"""The bundled scanner configuration must load before any rule can run."""
from pathlib import Path

import pytest
import yaml

RULES = Path(__file__).resolve().parents[1] / "nico" / "semgrep_rules_v1.yml"


def load_rules() -> list[dict]:
    try:
        document = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"Bundled Semgrep rules are not valid YAML: {exc}")
    assert isinstance(document, dict)
    rules = document.get("rules")
    assert isinstance(rules, list) and rules
    return rules


def test_all_bundled_semgrep_rules_load_with_unique_ids() -> None:
    rules = load_rules()
    assert {rule["id"] for rule in rules} == {
        "nico.python.dynamic-code-execution",
        "nico.python.subprocess-shell-true",
        "nico.python.unsafe-yaml-load",
        "nico.python.pickle-deserialization",
        "nico.javascript.dynamic-code-execution",
        "nico.javascript.child-process-exec",
        "nico.react.dangerously-set-inner-html",
        "nico.javascript.insecure-tls-validation",
    }
    assert len(rules) == 8


def test_tls_agent_pattern_keeps_options_inside_an_object() -> None:
    tls = next(rule for rule in load_rules()
               if rule["id"] == "nico.javascript.insecure-tls-validation")
    patterns = [item["pattern"] for item in tls["pattern-either"]]
    assert all(isinstance(pattern, str) for pattern in patterns)
    assert len(patterns) == 3
    assert patterns[-1].strip() == "new https.Agent({ ..., rejectUnauthorized: false, ... })"
    assert tls["severity"] == "ERROR"
    assert tls["languages"] == ["javascript", "typescript"]
