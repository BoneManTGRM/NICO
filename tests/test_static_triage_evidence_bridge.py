from __future__ import annotations

import nico.exact_snapshot_static_triage as static_triage
import nico.mid_assessment_handlers as mid_handlers
import nico.snapshot_assessment_handlers as snapshot_handlers
import nico.static_triage_evidence_bridge as bridge


def _outputs() -> dict:
    return {
        "scanner_worker": {
            "scan": {
                "scanner_results": [
                    {
                        "scanner": "nico-static",
                        "status": "passed",
                        "finding_count": 0,
                        "files_scanned": 250,
                    },
                    {
                        "scanner": "bandit",
                        "status": "passed",
                        "execution_status": "completed_with_findings",
                        "execution_completed": True,
                        "finding_count": 85,
                        "material_finding_count": 0,
                        "review_finding_count": 15,
                        "excluded_test_finding_count": 70,
                        "severity_counts": {"low": 80, "medium": 5},
                        "confidence_counts": {"high": 60, "medium": 25},
                        "triage_version": "nico-exact-snapshot-static-triage-v1",
                        "findings": [{"code": "source snippet must never cross the bridge"}],
                        "safe_output_preview": "source snippet must never cross the bridge",
                    },
                    {
                        "scanner": "semgrep",
                        "status": "passed",
                        "execution_status": "completed_with_findings",
                        "execution_completed": True,
                        "finding_count": 38,
                        "material_finding_count": 0,
                        "review_finding_count": 8,
                        "excluded_test_finding_count": 30,
                        "severity_counts": {"warning": 38},
                        "confidence_counts": {"unknown": 38},
                        "triage_version": "nico-exact-snapshot-static-triage-v1",
                        "findings": [{"lines": "another source snippet"}],
                    },
                ]
            }
        }
    }


def _delegate(_context: dict, _outputs_value: dict) -> dict:
    evidence = {
        "status": "attached",
        "scanner_results": [
            {"scanner": "nico-static", "status": "passed", "finding_count": 0, "files_scanned": 250},
            {"scanner": "bandit", "status": "passed"},
            {"scanner": "semgrep", "status": "passed"},
        ],
    }
    return {"status": "complete", "scanner_evidence": evidence, "evidence": evidence}


def test_bridge_restores_only_safe_structured_triage_fields(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_DELEGATE_HANDLER", _delegate)

    result = bridge.preserve_static_triage_attachment({"run_id": "midrun-1"}, _outputs())
    evidence = result["scanner_evidence"]
    by_scanner = {item["scanner"]: item for item in evidence["scanner_results"]}

    assert evidence["static_triage_evidence_bridge_version"] == bridge.BRIDGE_VERSION
    assert by_scanner["bandit"]["execution_completed"] is True
    assert by_scanner["bandit"]["material_finding_count"] == 0
    assert by_scanner["bandit"]["review_finding_count"] == 15
    assert by_scanner["bandit"]["excluded_test_finding_count"] == 70
    assert by_scanner["semgrep"]["finding_count"] == 38
    assert by_scanner["semgrep"]["severity_counts"] == {"warning": 38}
    assert "findings" not in by_scanner["bandit"]
    assert "safe_output_preview" not in by_scanner["bandit"]
    assert "source snippet must never cross the bridge" not in repr(result)
    assert "another source snippet" not in repr(result)
    assert result["evidence"] is result["scanner_evidence"]


def test_bridge_does_not_invent_missing_triage_values(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_DELEGATE_HANDLER", _delegate)
    outputs = _outputs()
    bandit = outputs["scanner_worker"]["scan"]["scanner_results"][1]
    bandit.pop("material_finding_count")
    bandit.pop("review_finding_count")

    result = bridge.preserve_static_triage_attachment({}, outputs)
    by_scanner = {item["scanner"]: item for item in result["scanner_evidence"]["scanner_results"]}

    assert "material_finding_count" not in by_scanner["bandit"]
    assert "review_finding_count" not in by_scanner["bandit"]
    assert by_scanner["bandit"]["execution_completed"] is True


def test_bridged_evidence_reaches_static_scoring(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_DELEGATE_HANDLER", _delegate)

    result = bridge.preserve_static_triage_attachment({}, _outputs())
    section = static_triage.triaged_static_section(
        {"code_signal_evidence": {"risk_pattern_hits": 0}},
        result["scanner_evidence"],
    )

    assert section["static_triage"]["structured_analyzers_completed"] == 2
    assert section["static_triage"]["material_finding_count"] == 0
    assert section["static_triage"]["review_finding_count"] == 23
    assert section["static_triage"]["excluded_test_finding_count"] == 100
    assert section["score"] >= 80
    assert section["status"] == "green"


def test_noncomplete_attachment_is_returned_unchanged(monkeypatch) -> None:
    pending = {"status": "pending", "evidence": {"scanner_status": "running"}}
    monkeypatch.setattr(bridge, "_DELEGATE_HANDLER", lambda _context, _outputs_value: pending)

    result = bridge.preserve_static_triage_attachment({}, _outputs())

    assert result is pending


def test_installer_binds_snapshot_and_mid_handlers_once(monkeypatch) -> None:
    fake = lambda _context, _outputs_value: {"status": "complete"}
    monkeypatch.setattr(snapshot_handlers, "_snapshot_evidence_attachment_handler", fake)
    monkeypatch.setattr(mid_handlers, "_snapshot_evidence_attachment_handler", fake)
    monkeypatch.delattr(snapshot_handlers, "_nico_static_triage_evidence_bridge_installed", raising=False)
    monkeypatch.setattr(bridge, "_DELEGATE_HANDLER", None)

    first = bridge.install_static_triage_evidence_bridge()
    delegate = bridge._DELEGATE_HANDLER
    second = bridge.install_static_triage_evidence_bridge()

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert delegate is fake
    assert bridge._DELEGATE_HANDLER is fake
    assert snapshot_handlers._snapshot_evidence_attachment_handler is bridge.preserve_static_triage_attachment
    assert mid_handlers._snapshot_evidence_attachment_handler is bridge.preserve_static_triage_attachment
