from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def stub_live_full_run_repository_evidence(monkeypatch):
    """Keep tests deterministic while production full-runs use authorized GitHub read APIs."""

    def collect(context):
        return {
            "status": "attached",
            "evidence_id": f"evidence_{context['run_id']}",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "source": "github_api_read_only",
            "authorization_scope": context.get("authorization_scope") or "repository assessment only",
            "timeframe_days": context.get("timeframe_days") or 180,
            "repository_metadata": {"default_branch": "main", "visibility": "public", "private": False},
            "file_evidence": {"files_profiled": 12, "tree_paths_seen": 40, "sampled_paths": ["README.md", "requirements.txt"]},
            "activity_evidence": {"commits_returned": 8, "pull_requests_returned": 4, "merged_pull_requests": 3, "open_pull_requests": 1},
            "workflow_evidence": {"workflow_file_count": 2, "workflow_run_count": 10, "successful_runs": 9, "non_success_runs": 1},
            "dependency_evidence": {"dependency_entries": 20, "manifest_paths": ["requirements.txt"], "lockfile_paths": []},
            "architecture_evidence": {"source_file_count": 25, "test_path_count": 6, "documentation_path_count": 4},
            "code_signal_evidence": {"risk_pattern_hits": 0, "potential_secret_pattern_hits": 0},
            "unavailable_data_notes": [],
            "retention_note": "Summarized repository evidence only.",
            "idempotent_reuse": False,
            "human_review_required": True,
        }

    def collect_complexity(context):
        return {
            "status": "attached",
            "evidence_id": f"complexity_{context['run_id']}",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "source": "github_api_bounded_complexity_analysis",
            "analyzer_version": "nico-bounded-complexity-v1",
            "files_analyzed": 20,
            "python_files_analyzed": 20,
            "javascript_typescript_files_analyzed": 0,
            "python_parse_failures": 0,
            "total_source_loc": 1800,
            "functions_measured": 40,
            "average_cyclomatic_complexity": 3.5,
            "median_cyclomatic_complexity": 2.0,
            "p90_cyclomatic_complexity": 7,
            "maximum_cyclomatic_complexity": 9,
            "high_complexity_functions": 0,
            "very_high_complexity_functions": 0,
            "high_complexity_ratio": 0.0,
            "long_functions": 0,
            "deep_nesting_functions": 0,
            "maximum_nesting": 3,
            "import_edges": 32,
            "internal_import_edges": 16,
            "average_fan_out": 1.6,
            "maximum_fan_out": 6,
            "hotspots": [],
            "duplicate_evidence": {
                "duplicate_block_groups": 0,
                "duplicate_line_positions": 0,
                "normalized_source_lines": 1500,
                "duplicate_line_ratio": 0.0,
                "samples": [],
            },
            "unavailable_data_notes": [],
            "retention_note": "Only bounded numeric and path-level complexity evidence is retained.",
            "guardrail": "Complexity evidence covers the authorized sampled source files only.",
            "idempotent_reuse": False,
            "human_review_required": True,
        }

    monkeypatch.setattr("nico.full_assessment_repository_evidence.collect_repository_evidence", collect)
    monkeypatch.setattr("nico.full_assessment_complexity_repository.collect_repository_complexity_evidence", collect_complexity)
