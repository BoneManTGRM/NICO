from pathlib import Path


ROUTE = Path("apps/web/app/api/provider-onboarding/[...path]/route.ts")


def test_browser_provider_proxy_exposes_only_capability_truth_and_ordinary_preflight() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'const CAPABILITIES = "/providers/capabilities"' in source
    assert 'const PREFLIGHT = "/providers/onboarding/preflight"' in source
    assert "provider rollout administration is server-only" in source.lower()
    assert "/rollout" not in source
    assert "Only provider capability truth and ordinary onboarding preflight" in source


def test_browser_provider_proxy_never_forwards_admin_or_provider_credentials() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert "Deliberately do not forward x-nico-admin-token" in source
    assert 'headers.set("X-NICO-Admin-Token"' not in source
    assert 'headers.set("Authorization"' not in source
    assert 'headers.set("PRIVATE-TOKEN"' not in source
    assert "credential_detail_exposed: false" in source
    assert "human_review_required: true" in source
    assert "client_delivery_allowed: false" in source


def test_browser_provider_proxy_uses_one_fail_closed_backend_origin() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert "NICO_API_URL" in source
    assert "NICO_BACKEND_URL" in source
    assert "NEXT_PUBLIC_NICO_API_URL" in source
    assert "values.length === 1" in source
    assert "provider_backend_configuration_conflict" in source
    assert "redirect: \"manual\"" in source
    assert "AbortSignal.timeout(TIMEOUT_MS)" in source
