from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_active_run_uses_pending_persistence_language() -> None:
    text = source()

    assert 'verificationPending: "Verification pending"' in text
    assert 'verificationPending: "Verificación pendiente"' in text
    assert 'if (!terminal) return copy.verificationPending;' in text
    assert 'persistenceStatus(result.persistence, phase, copy)' in text


def test_verified_persistence_requires_explicit_backend_proof() -> None:
    text = source()

    assert 'persistence?.durable === true || persistence?.durability_verified === true' in text
    assert 'verifiedPersistentStorage: "Verified persistent storage"' in text
    assert 'verifiedPersistentStorage: "Almacenamiento persistente verificado"' in text
    assert 'if (verified) return copy.verifiedPersistentStorage;' in text


def test_not_verified_is_reserved_for_terminal_unproven_runs() -> None:
    text = source()

    assert 'const terminal = ["review_required", "complete", "failed", "timed_out"].includes(phase);' in text
    assert 'if (!terminal) return copy.verificationPending;' in text
    assert 'return copy.notVerified;' in text
    assert 'result.persistence?.durable ? copy.yes : result.persistence?.recorded ? copy.recorded : copy.notVerified' not in text
