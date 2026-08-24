from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "apps/web/app/assessment/repositoryProvider.ts"
BRIDGE = ROOT / "apps/web/app/assessment/AssessmentProviderParityBridge.tsx"


def test_spanish_provider_surface_uses_localized_coordinate_examples() -> None:
    provider = PROVIDER.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")

    assert 'placeholderEs: "propietario/repositorio"' in provider
    assert 'placeholderEs: "grupo/proyecto"' in provider
    assert 'placeholderEs: "espacio-trabajo/repositorio"' in provider
    assert 'placeholderEs: "organizacion/proyecto/repositorio"' in provider
    assert "providerPlaceholder(provider, locale)" in bridge
    assert "providerOption(provider).placeholder" not in bridge
    assert "providerOption(readRepositoryProvider()).placeholder" not in bridge


def test_english_provider_examples_remain_unchanged_for_the_english_site() -> None:
    provider = PROVIDER.read_text(encoding="utf-8")

    assert 'placeholder: "owner/repository"' in provider
    assert 'placeholder: "group/project"' in provider
    assert 'placeholder: "workspace/repository"' in provider
    assert 'placeholder: "organization/project/repository"' in provider
