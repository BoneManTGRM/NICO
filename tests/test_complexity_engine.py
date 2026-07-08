from __future__ import annotations

from nico.complexity_engine import build_complexity_profile
from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts


def test_complexity_engine_profiles_python_and_typescript_sources(tmp_path):
    repo = tmp_path / "repo"
    (repo / "nico").mkdir(parents=True)
    (repo / "apps" / "web" / "app").mkdir(parents=True)
    (repo / "requirements.txt").write_text("fastapi==0.139.0\nrequests==2.33.0\n", encoding="utf-8")
    (repo / "nico" / "app.py").write_text(
        "import requests\n\n"
        "def alpha(value):\n"
        "    if value:\n"
        "        return beta(value)\n"
        "    return None\n\n"
        "def beta(value):\n"
        "    for item in value:\n"
        "        if item:\n"
        "            print(item)\n"
        "    return value\n",
        encoding="utf-8",
    )
    (repo / "apps" / "web" / "app" / "page.tsx").write_text(
        "import React from 'react';\n"
        "export default function Page() {\n"
        "  const ok = true ? 1 : 0;\n"
        "  return <main>{ok}</main>;\n"
        "}\n",
        encoding="utf-8",
    )

    profile = build_complexity_profile(repo)

    assert profile["artifact_schema"] == "nico.complexity.v1"
    assert profile["source_file_count"] == 2
    assert profile["total_functions"] >= 2
    assert profile["call_graph_edge_count"] >= 2
    assert profile["manifest_dependency_count"] == 2
    assert profile["complexity_score"] >= 35
    assert profile["hotspots"]
    assert any("Complexity engine analyzed" in item for item in profile["evidence"])


def test_complexity_artifact_updates_architecture_and_velocity_sections():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 72,
                "status": "yellow",
                "summary": "Hosted layout only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker."],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 73,
                "status": "yellow",
                "summary": "Hosted velocity only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Precise story-point expectation and deeper complexity analysis require stakeholder context and human review."],
            },
        ],
        "findings": [],
    }
    artifact = {
        "tools": {},
        "complexity_engine": {
            "artifact_schema": "nico.complexity.v1",
            "complexity_score": 88,
            "architecture_score": 90,
            "velocity_score": 88,
            "risk_level": "low",
            "evidence": ["Complexity engine analyzed 12 source file(s), 900 source LOC, and 45 function-like units."],
            "findings": [],
            "hotspots": [
                {
                    "path": "nico/app.py",
                    "hotspot_score": 12.4,
                    "loc": 120,
                    "cyclomatic_complexity": 6,
                    "churn": 14,
                }
            ],
        },
    }

    updated = attach_scanner_worker_artifacts(result, {"scanner_worker_artifact": artifact})
    architecture = next(item for item in updated["sections"] if item["id"] == "architecture_debt")
    velocity = next(item for item in updated["sections"] if item["id"] == "velocity_complexity")

    assert updated["complexity_engine"]["complexity_score"] == 88
    assert architecture["score"] == 90
    assert not architecture["unavailable"]
    assert any("call-graph" in architecture["summary"] for _ in [0])
    assert velocity["score"] == 88
    assert any("Complexity hotspot" in item for item in velocity["findings"])
