from __future__ import annotations

from nico.source_signal_analysis_v2 import analyze_source_signals


def test_detector_definitions_comments_and_strings_do_not_become_code_risks() -> None:
    result = analyze_source_signals(
        {
            "nico/detector.py": """
RISK_PATTERNS = [(\"tls_verify_disabled\", r\"verify=False\")]
# requests.get(url, verify=False)
MESSAGE = \"exec(user_text) and rejectUnauthorized: false\"
""",
            "docs/security.md": "Use `verify=False` only as a negative example.",
            "tests/test_fixture.py": "def test_fixture():\n    exec('pass')\n",
        }
    )

    assert result["risks"] == []
    assert len(result["excluded_non_production_risks"]) == 1
    assert result["comments_and_strings_excluded"] is True


def test_real_python_and_typescript_execution_risks_retain_exact_locations() -> None:
    result = analyze_source_signals(
        {
            "nico/http_client.py": "import requests\nresponse = requests.get(url, verify=False)\n",
            "apps/web/app/page.tsx": "const node = document.body;\nnode.innerHTML = content;\n",
        }
    )

    assert len(result["risk_records"]) == 2
    by_rule = {item["rule_id"]: item for item in result["risk_records"]}
    assert by_rule["tls_verify_disabled"]["path"] == "nico/http_client.py"
    assert by_rule["tls_verify_disabled"]["line"] == 2
    assert "verify=False" in by_rule["tls_verify_disabled"]["source_excerpt"]
    assert by_rule["js_inner_html"]["path"] == "apps/web/app/page.tsx"
    assert by_rule["js_inner_html"]["line"] == 2


def test_example_environment_placeholders_are_separate_from_secret_risk() -> None:
    result = analyze_source_signals(
        {
            ".env.example": "DATABASE_URL=postgresql://user:password@localhost:5432/nico\n",
            "nico/settings.py": "TOKEN='this-is-a-long-secret-value'\n",
        }
    )

    assert len(result["verified_example_placeholder_secrets"]) == 1
    assert len(result["secrets"]) == 1
    assert ".env.example" in result["verified_example_placeholder_secrets"][0]
    assert "nico/settings.py" in result["secrets"][0]


def test_source_detector_classifies_observations_without_claiming_review() -> None:
    files = {
        "src/runner.py": "exec(command)\n",
        "tests/test_runner.py": "exec(command)\n",
    }
    result = analyze_source_signals(files)
    observation = result["risk_records"][0]
    excluded = result["excluded_non_production_risks"][0]
    assert observation["semantic_class"] == "source_observation"
    assert observation["disposition_state"] == "not_dispositioned"
    assert excluded["semantic_class"] == "excluded_non_production_observation"
    assert excluded["disposition_state"] == "not_dispositioned"
    assert observation["observation_id"] != excluded["observation_id"]
    assert analyze_source_signals(dict(reversed(list(files.items()))))["risk_records"] == result["risk_records"]
    assert observation["rule_id"] == "python_eval_exec"
    assert observation["path"] == "src/runner.py"
    assert observation["line"] == 1
    assert observation["source_excerpt"] == "exec(command)"


def test_two_executable_observations_on_one_line_have_distinct_stable_identities() -> None:
    records = analyze_source_signals({"src/runner.py": "exec(first); exec(second)\n"})["risk_records"]
    assert len(records) == 2
    assert len({record["observation_id"] for record in records}) == 2
    assert records == analyze_source_signals({"src/runner.py": "exec(first); exec(second)\n"})["risk_records"]
