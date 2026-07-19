from types import SimpleNamespace

from nico.express_decision_quality_v17 import (
    _is_language_false_positive,
    _reconcile_ci_statement,
    normalize_express_decision_quality,
)


TSX_FALSE_POSITIVES = [
    "Python Eval Exec in apps/web/app/AssessmentExpressRecoveryGuard.tsx:163",
    "Python Eval Exec in apps/web/app/AssessmentMidLiveStatusTransport.tsx:316",
    "Python Eval Exec in apps/web/app/AssessmentProgressIntegrityGuard.tsx:239",
    "Python Eval Exec in apps/web/app/AssessmentStatusOutcomeGuard.tsx:220",
    "Python Eval Exec in apps/web/app/AssessmentStatusResilience.tsx:273",
]


def test_named_tsx_python_eval_exec_hits_are_language_mismatches() -> None:
    assert all(_is_language_false_positive(value) for value in TSX_FALSE_POSITIVES)
    assert _is_language_false_positive(
        "apps/web/app/example.tsx:10: python_eval_exec - Dynamic code execution should be reviewed."
    )
    assert not _is_language_false_positive(
        "nico/runtime.py:10: python_eval_exec - Dynamic code execution should be reviewed."
    )


def test_language_mismatches_are_removed_from_sections_and_repair_intelligence() -> None:
    result = {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [
            {
                "id": "static_analysis",
                "evidence": TSX_FALSE_POSITIVES.copy(),
                "findings": TSX_FALSE_POSITIVES.copy(),
                "unavailable": [],
            }
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "title": value,
                    "category": "static_analysis",
                    "severity": "critical",
                    "priority": "critical",
                    "status": "candidate",
                }
                for value in TSX_FALSE_POSITIVES
            ]
            + [
                {
                    "title": "Bandit analyzer failed and requires review",
                    "category": "scanner_evidence",
                    "severity": "high",
                    "priority": "high",
                    "status": "candidate",
                }
            ]
        },
    }

    normalized = normalize_express_decision_quality(result)
    section = normalized["sections"][0]
    assert section["evidence"] == []
    assert section["findings"] == []
    candidates = normalized["repair_intelligence"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["title"] == "Bandit analyzer failed and requires review"
    assert candidates[0]["severity"] == "review"
    assert candidates[0]["priority"] == "review"
    assert candidates[0]["confidence"] == "review-limited"


def test_unverified_secret_candidates_are_one_parallel_triage_workstream() -> None:
    result = {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "sections": [],
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Potential secret exposure in nico/a.py:1",
                    "category": "secret_exposure",
                    "severity": "critical",
                    "status": "candidate",
                    "affected_files": ["nico/a.py"],
                    "evidence": ["generic token-name match"],
                },
                {
                    "title": "Potential secret exposure in nico/b.py:2",
                    "category": "secret_exposure",
                    "severity": "critical",
                    "status": "candidate",
                    "affected_files": ["nico/b.py"],
                    "evidence": ["history hit pending triage"],
                },
            ]
        },
    }

    normalized = normalize_express_decision_quality(result)
    candidates = normalized["repair_intelligence"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["candidate_id"] == "express_secret_candidate_triage_group"
    assert candidates[0]["severity"] == "review"
    assert candidates[0]["status"] == "candidate_pending_human_triage"
    assert candidates[0]["affected_files"] == ["nico/a.py", "nico/b.py"]


def test_ci_reconciliation_replaces_repeated_other_unknown_once() -> None:
    raw = (
        "GitHub Actions workflow runs returned in assessment window: "
        "100; success=90; non-success=5; other/unknown=5; other/unknown=5; other/unknown=5."
    )
    reconciled = _reconcile_ci_statement(raw)
    assert reconciled.count("other/unknown=") == 1
    assert "100; success=90; non-success=5; other/unknown=5" in reconciled
