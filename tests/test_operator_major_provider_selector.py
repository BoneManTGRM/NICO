from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "apps/web/app/assessment/repositoryProvider.ts"
BRIDGE = ROOT / "apps/web/app/assessment/AssessmentProviderParityBridge.tsx"
PROXY = ROOT / "apps/web/app/api/nico/providers/operator/comprehensive-intake/route.ts"
PAGE = ROOT / "apps/web/app/assessment/AssessmentPage.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_major_hosted_provider_machine_values_and_operator_labels_are_exposed():
    provider = _text(PROVIDER)
    bridge = _text(BRIDGE)
    for machine_value in ('"github"', '"gitlab"', '"bitbucket_cloud"', '"azure_devops"'):
        assert machine_value in provider
    for label in ("GitHub", "GitLab", "Bitbucket", "Azure DevOps"):
        assert label in provider
    assert '"Repository provider"' in bridge
    assert '"Proveedor del repositorio"' in bridge
    assert '"Repository URL or identifier"' in bridge
    assert '"URL o identificador del repositorio"' in bridge


def test_provider_examples_match_the_operator_runtime_coordinates():
    provider = _text(PROVIDER)
    assert 'placeholder: "owner/repository"' in provider
    assert 'placeholder: "group/project"' in provider
    assert 'placeholder: "workspace/repository"' in provider
    assert 'placeholder: "organization/project/repository"' in provider
    assert 'provider_organization: parts[0]' in provider
    assert 'provider_project: parts[1]' in provider


def test_full_url_detection_uses_exact_approved_hosts_not_substring_matching():
    provider = _text(PROVIDER)
    assert 'host === "github.com"' in provider
    assert 'host === "gitlab.com"' in provider
    assert 'host === "bitbucket.org"' in provider
    assert 'host === "dev.azure.com"' in provider
    assert 'VISUAL_STUDIO_HOST' in provider
    for unsafe in (
        'host.includes("github.com")',
        'host.includes("gitlab.com")',
        'host.includes("bitbucket.org")',
        'host.includes("dev.azure.com")',
        'host.endsWith("github.com")',
        'host.endsWith("gitlab.com")',
        'host.endsWith("bitbucket.org")',
        'host.endsWith("dev.azure.com")',
    ):
        assert unsafe not in provider
    assert 'url.username ||' in provider
    assert 'url.password ||' in provider
    assert 'url.port ||' in provider
    assert 'url.search ||' in provider
    assert 'url.hash' in provider


def test_azure_urls_require_canonical_git_shape():
    provider = _text(PROVIDER)
    assert 'parts[2].toLowerCase() !== "_git"' in provider
    assert 'parts[1].toLowerCase() !== "_git"' in provider
    assert 'host.match(VISUAL_STUDIO_HOST)' in provider


def test_provider_choice_survives_locale_but_operator_token_is_memory_only():
    provider = _text(PROVIDER)
    bridge = _text(BRIDGE)
    assert 'window.sessionStorage.getItem(REPOSITORY_PROVIDER_STORAGE_KEY)' in provider
    assert 'window.sessionStorage.setItem(REPOSITORY_PROVIDER_STORAGE_KEY, provider)' in provider
    assert "OPERATOR_ADMIN_TOKEN_STORAGE_KEY" not in provider
    assert "localStorage" not in provider
    assert 'const operatorTokenRef = useRef("")' in bridge
    assert 'operatorTokenRef.current = value' in bridge
    assert 'operatorTokenRef.current.trim()' in bridge
    assert "sessionStorage" not in bridge


def test_github_keeps_existing_proven_intake_while_other_providers_use_operator_runtime():
    bridge = _text(BRIDGE)
    assert 'PUBLIC_INTAKE_PATH = "/api/nico/assessment/comprehensive-intake"' in bridge
    assert 'OPERATOR_INTAKE_PATH = "/api/nico/providers/operator/comprehensive-intake"' in bridge
    assert 'if (selectedProvider === "github") return originalFetch(input, init);' in bridge
    assert 'headers.set("X-NICO-Admin-Token", token)' in bridge
    assert 'provider: normalized.provider' in bridge
    assert 'nextBody.provider_organization = normalized.provider_organization' in bridge
    assert 'nextBody.provider_project = normalized.provider_project' in bridge


def test_browser_code_never_contains_provider_credentials():
    browser_sources = _text(PROVIDER) + _text(BRIDGE)
    for secret_name in (
        "GITLAB_TOKEN",
        "GITLAB_ACCESS_TOKEN",
        "BITBUCKET_TOKEN",
        "BITBUCKET_APP_PASSWORD",
        "AZURE_DEVOPS_TOKEN",
        "AZURE_DEVOPS_PAT",
        "GITHUB_TOKEN",
    ):
        assert secret_name not in browser_sources


def test_operator_proxy_preserves_existing_admin_boundary_without_server_secret_injection():
    proxy = _text(PROXY)
    assert 'request.headers.get("x-nico-admin-token")' in proxy
    assert '"X-NICO-Admin-Token": adminToken' in proxy
    assert 'process.env.NICO_ADMIN_TOKEN' not in proxy
    assert 'process.env.NICO_ADMIN_WRITE_TOKEN' not in proxy
    assert 'redirect: "manual"' in proxy
    assert 'operator_provider_intake_redirect_blocked' in proxy
    assert 'sameOrigin(request)' in proxy
    assert 'Cache-Control' in proxy and 'no-store' in proxy


def test_provider_bridge_is_mounted_before_the_existing_workspace():
    page = _text(PAGE)
    bridge_index = page.index("<AssessmentProviderParityBridge")
    workspace_index = page.index("<AssessmentWorkspace")
    assert bridge_index < workspace_index
