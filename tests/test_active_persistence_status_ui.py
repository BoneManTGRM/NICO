from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"


def source() -> str:
    return "\n".join(
        (ASSESSMENT / name).read_text(encoding="utf-8")
        for name in (
            "AssessmentWorkspace.tsx",
            "assessmentModel.ts",
            "assessmentStatus.ts",
            "assessmentCopy.ts",
        )
    )


def test_active_run_uses_pending_persistence_language() -> None:
    text = source()

    assert 'verificationPending: "Verification pending"' in text
    assert 'verificationPending: "Verificación pendiente"' in text
    assert 'persistenceStatus(result.persistence, phase, copy)' in text
    assert "copy.notVerified" in text
    assert "copy.verificationPending" in text


def test_verified_persistence_requires_explicit_backend_proof() -> None:
    text = source()

    assert 'persistence?.durable === true' in text
    assert 'persistence?.durability_verified === true' in text
    assert 'verifiedPersistentStorage: "Verified persistent storage"' in text
    assert 'verifiedPersistentStorage: "Almacenamiento persistente verificado"' in text
    assert 'return copy.verifiedPersistentStorage' in text


def test_not_verified_is_reserved_for_terminal_or_unavailable_unproven_runs() -> None:
    text = source()

    for terminal in (
        '"review_required"',
        '"complete"',
        '"unavailable"',
        '"failed"',
        '"timed_out"',
    ):
        assert terminal in text
    assert ".includes(phase)" in text
    assert "copy.notVerified" in text
    assert "copy.verificationPending" in text
    assert 'result.persistence?.durable ? copy.yes : result.persistence?.recorded ? copy.recorded : copy.notVerified' not in text
