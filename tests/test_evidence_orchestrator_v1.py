from pathlib import Path

import pytest

from nico.evidence_execution_contract_v1 import EvidenceContractViolation, FailureClass
from nico.evidence_orchestrator_v1 import (
    ScannerAttempt,
    ScannerSpec,
    execute_scanner,
    finalize_evidence,
    require_exact_revision,
)


def test_completed_scanner_retains_hashed_artifacts(tmp_path: Path):
    def runner(spec, attempt):
        return ScannerAttempt(0, b"out", b"", b"{}", "a", "b", "1.0")

    record = execute_scanner(
        ScannerSpec("bandit", ("bandit", "-r", ".")),
        immutable_revision="abc",
        artifact_dir=tmp_path,
        runner=runner,
        coverage_scope={"paths": ["."]},
    )
    assert record.complete
    assert Path(record.raw_artifact).exists()
    assert len(record.artifact_sha256) == 64


def test_retry_is_bounded_and_infrastructure_only(tmp_path: Path):
    attempts = []

    def runner(spec, attempt):
        attempts.append(attempt)
        if attempt == 0:
            return ScannerAttempt(None, b"", b"network", b"network", "a", "b", "1.0", failure_class=FailureClass.INFRASTRUCTURE, failure_reason="network")
        return ScannerAttempt(0, b"ok", b"", b"{}", "c", "d", "1.0")

    record = execute_scanner(
        ScannerSpec("semgrep", ("semgrep", "scan"), max_retries=1),
        immutable_revision="abc",
        artifact_dir=tmp_path,
        runner=runner,
        coverage_scope={},
    )
    assert attempts == [0, 1]
    assert record.complete


def test_incomplete_required_scanner_blocks_normal_finalization(tmp_path: Path):
    def runner(spec, attempt):
        return ScannerAttempt(2, b"", b"bad config", b"bad config", "a", "b", "1.0", failure_class=FailureClass.SOURCE_DETERMINISTIC, failure_reason="bad config")

    record = execute_scanner(
        ScannerSpec("eslint", ("eslint", "."), max_retries=3),
        immutable_revision="abc",
        artifact_dir=tmp_path,
        runner=runner,
        coverage_scope={},
    )
    with pytest.raises(EvidenceContractViolation):
        finalize_evidence([record], required_tools=["eslint"])
    degraded = finalize_evidence([record], required_tools=["eslint"], allow_degraded=True)
    assert degraded["client_delivery_allowed"] is False
    assert degraded["score_normalization_allowed"] is False


def test_exact_revision_is_mandatory(tmp_path: Path):
    def runner(spec, attempt):
        return ScannerAttempt(0, b"", b"", b"{}", "a", "b", "1.0")

    record = execute_scanner(
        ScannerSpec("pip-audit", ("pip-audit",)),
        immutable_revision="wrong",
        artifact_dir=tmp_path,
        runner=runner,
        coverage_scope={},
    )
    with pytest.raises(EvidenceContractViolation):
        require_exact_revision([record], "expected")
