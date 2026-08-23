from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE_PROOF = ROOT / "scripts" / "mobile_restart_live_acceptance_v1.py"
SPANISH_PROOF = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v1.py"
PROVIDER_BRIDGE = (
    ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentProviderParityBridge.tsx"
)

ENGLISH_REPOSITORY_LABEL = "Repository URL or identifier"
SPANISH_REPOSITORY_LABEL = "URL o identificador del repositorio"
LEGACY_ENGLISH_LABEL = "Repository owner/name or GitHub URL"
LEGACY_SPANISH_LABEL = "Propietario/nombre del repositorio o URL de GitHub"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_production_proof_tracks_provider_neutral_repository_label() -> None:
    mobile = _text(MOBILE_PROOF)
    bridge = _text(PROVIDER_BRIDGE)

    assert f'REPOSITORY_LABEL = "{ENGLISH_REPOSITORY_LABEL}"' in mobile
    assert "page.get_by_label(REPOSITORY_LABEL).fill(args.repository)" in mobile
    assert f'return locale === "es-MX" ? "{SPANISH_REPOSITORY_LABEL}" : "{ENGLISH_REPOSITORY_LABEL}";' in bridge
    assert LEGACY_ENGLISH_LABEL not in mobile


def test_spanish_production_proof_tracks_provider_neutral_repository_label() -> None:
    spanish = _text(SPANISH_PROOF)
    bridge = _text(PROVIDER_BRIDGE)

    assert f'SPANISH_REPO_LABEL = "{SPANISH_REPOSITORY_LABEL}"' in spanish
    assert "page.get_by_label(SPANISH_REPO_LABEL).fill(args.repository)" in spanish
    assert SPANISH_REPOSITORY_LABEL in bridge
    assert LEGACY_SPANISH_LABEL not in spanish
