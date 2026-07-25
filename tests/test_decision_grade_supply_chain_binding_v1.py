from __future__ import annotations

from nico.decision_grade_supply_chain_binding_v1 import wrap_report_builder_with_supply_chain


def _delegate(*args, **kwargs):
    return {
        "repository": kwargs.get("repository", "owner/repo"),
        "commit_sha": kwargs.get("commit_sha", "a" * 40),
        "report_package": {"json": {}, "quality": {}},
    }


def test_binding_attaches_supply_chain_evidence_to_all_machine_readable_surfaces() -> None:
    wrapped = wrap_report_builder_with_supply_chain(_delegate)
    result = wrapped(
        repository="owner/repo",
        commit_sha="a" * 40,
        source_files={
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
            "package-lock.json": '{"lockfileVersion":3}',
        },
    )

    evidence = result["supply_chain_evidence"]
    assert evidence["lockfile_completeness"]["complete"] is True
    assert result["report_package"]["supply_chain_evidence"] == evidence
    assert result["report_package"]["json"]["supply_chain_evidence"] == evidence
    assert result["report_package"]["quality"]["supply_chain_status"] == "complete"
    assert evidence["client_delivery_allowed"] is False


def test_missing_file_content_is_not_misrepresented_as_clean() -> None:
    wrapped = wrap_report_builder_with_supply_chain(_delegate)
    result = wrapped(repository="owner/repo", commit_sha="b" * 40)

    evidence = result["supply_chain_evidence"]
    assert evidence["status"] == "not_assessed"
    assert evidence["vulnerability_register"] == []
    assert evidence["limitations"]
    assert result["report_package"]["quality"]["supply_chain_status"] == "not_assessed"


def test_stage_bound_source_files_are_supported() -> None:
    wrapped = wrap_report_builder_with_supply_chain(_delegate)
    result = wrapped(
        stage_results={
            "repository_and_delivery_evidence": {
                "source_files": {
                    "requirements.txt": "fastapi==1.0\n",
                    "uv.lock": "version = 1\n",
                }
            }
        }
    )

    assert result["supply_chain_evidence"]["lockfile_completeness"]["complete"] is True
    assert len(result["supply_chain_evidence"]["dependency_inventory"]) == 1


def test_wrapper_is_idempotent() -> None:
    first = wrap_report_builder_with_supply_chain(_delegate)
    second = wrap_report_builder_with_supply_chain(first)

    assert second is first
