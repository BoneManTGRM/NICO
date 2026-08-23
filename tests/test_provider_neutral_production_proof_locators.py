from pathlib import Path

from scripts.provider_neutral_repository_locator_contract_v1 import (
    ENGLISH_REPOSITORY_LABEL,
    LEGACY_ENGLISH_REPOSITORY_LABEL,
    SPANISH_REPOSITORY_LABEL,
    install_provider_neutral_repository_locator,
)


ROOT = Path(__file__).resolve().parents[1]


class _RawPage:
    def get_by_label(self, label, *args, **kwargs):
        return {"label": label, "args": args, "kwargs": kwargs}


class _WrappedPage:
    def __init__(self):
        self._page = _RawPage()


class _SingleDispatch:
    _SingleDispatchPage = _WrappedPage


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_mobile_proof_adapter_maps_only_the_obsolete_github_label():
    install_provider_neutral_repository_locator(_SingleDispatch)
    page = _WrappedPage()

    mapped = page.get_by_label(LEGACY_ENGLISH_REPOSITORY_LABEL, exact=True)
    assert mapped["label"] == ENGLISH_REPOSITORY_LABEL
    assert mapped["kwargs"] == {"exact": True}

    ordinary = page.get_by_label("Client name, optional")
    assert ordinary["label"] == "Client name, optional"


def test_locator_installer_is_idempotent():
    install_provider_neutral_repository_locator(_SingleDispatch)
    first = _SingleDispatch._SingleDispatchPage.get_by_label
    install_provider_neutral_repository_locator(_SingleDispatch)
    assert _SingleDispatch._SingleDispatchPage.get_by_label is first


def test_production_mobile_and_ios_entrypoints_install_current_repository_contract():
    for relative in (
        "scripts/mobile_restart_live_acceptance_v5.py",
        "scripts/mobile_restart_live_acceptance_v6.py",
    ):
        source = _text(relative)
        assert "install_provider_neutral_repository_locator(single_dispatch)" in source
        assert "provider_neutral_repository_locator_contract_v1" in source


def test_spanish_production_entrypoint_uses_provider_neutral_label():
    source = _text("scripts/spanish_comprehensive_live_acceptance_v3.py")
    assert "base.SPANISH_REPO_LABEL = SPANISH_REPOSITORY_LABEL" in source
    assert "provider_neutral_repository_locator_contract_v1" in source
    assert SPANISH_REPOSITORY_LABEL == "URL o identificador del repositorio"


def test_current_labels_are_provider_neutral_and_legacy_value_is_compatibility_only():
    assert ENGLISH_REPOSITORY_LABEL == "Repository URL or identifier"
    assert SPANISH_REPOSITORY_LABEL == "URL o identificador del repositorio"
    assert LEGACY_ENGLISH_REPOSITORY_LABEL == "Repository owner/name or GitHub URL"

    helper = _text("scripts/provider_neutral_repository_locator_contract_v1.py")
    mobile = _text("scripts/mobile_restart_live_acceptance_v5.py")
    ios = _text("scripts/mobile_restart_live_acceptance_v6.py")
    spanish = _text("scripts/spanish_comprehensive_live_acceptance_v3.py")
    assert LEGACY_ENGLISH_REPOSITORY_LABEL in helper
    assert LEGACY_ENGLISH_REPOSITORY_LABEL not in mobile
    assert LEGACY_ENGLISH_REPOSITORY_LABEL not in ios
    assert "Propietario/nombre del repositorio o URL de GitHub" not in spanish
