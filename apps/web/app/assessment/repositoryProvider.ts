export type RepositoryProvider = "github" | "gitlab" | "bitbucket_cloud" | "azure_devops";

export type RepositoryProviderOption = {
  value: RepositoryProvider;
  label: string;
  placeholder: string;
};

export type NormalizedRepositorySelection = {
  provider: RepositoryProvider;
  repository: string;
  provider_organization?: string;
  provider_project?: string;
};

export const REPOSITORY_PROVIDER_STORAGE_KEY = "nico.comprehensive.repository-provider.v1";
export const OPERATOR_ADMIN_TOKEN_STORAGE_KEY = "nico.operator.admin-token.session.v1";

export const REPOSITORY_PROVIDER_OPTIONS: readonly RepositoryProviderOption[] = [
  {value: "github", label: "GitHub", placeholder: "owner/repository"},
  {value: "gitlab", label: "GitLab", placeholder: "group/project"},
  {value: "bitbucket_cloud", label: "Bitbucket", placeholder: "workspace/repository"},
  {value: "azure_devops", label: "Azure DevOps", placeholder: "organization/project/repository"},
] as const;

const SAFE_SEGMENT = /^[A-Za-z0-9_.-]+$/;

function safeSegment(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized || normalized === "." || normalized === ".." || !SAFE_SEGMENT.test(normalized)) {
    throw new Error(`${field}_invalid`);
  }
  return normalized;
}

function stripGitSuffix(value: string): string {
  return value.toLowerCase().endsWith(".git") ? value.slice(0, -4) : value;
}

function absoluteRepositoryUrl(value: string): URL | null {
  const raw = value.trim();
  if (!/^https:\/\//i.test(raw)) return null;
  try {
    const url = new URL(raw);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.port ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

export function detectRepositoryProvider(value: string): RepositoryProvider | null {
  const url = absoluteRepositoryUrl(value);
  if (!url) return null;
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (host === "github.com") return "github";
  if (host === "gitlab.com") return "gitlab";
  if (host === "bitbucket.org") return "bitbucket_cloud";
  if (host === "dev.azure.com" || /^[a-z0-9.-]+\.visualstudio\.com$/i.test(host)) return "azure_devops";
  return null;
}

function pathSegments(url: URL): string[] {
  return url.pathname.split("/").map((part) => part.trim()).filter(Boolean);
}

function normalizeShorthand(provider: RepositoryProvider, value: string): NormalizedRepositorySelection {
  const raw = value.trim().replace(/^\/+|\/+$/g, "");
  if (!raw || raw.includes("://") || raw.includes("\\") || /[\r\n\0]/.test(raw)) {
    throw new Error("provider_repository_invalid");
  }
  const parts = raw.split("/").map((part) => safeSegment(part, "provider_repository"));
  if (provider === "github") {
    if (parts.length !== 2) throw new Error("github_repository_coordinates_invalid");
    return {provider, repository: `${parts[0]}/${stripGitSuffix(parts[1])}`};
  }
  if (provider === "gitlab") {
    if (parts.length < 2) throw new Error("gitlab_repository_coordinates_invalid");
    parts[parts.length - 1] = stripGitSuffix(parts[parts.length - 1]);
    return {provider, repository: parts.join("/")};
  }
  if (provider === "bitbucket_cloud") {
    if (parts.length !== 2) throw new Error("bitbucket_repository_coordinates_invalid");
    return {provider, repository: `${parts[0]}/${stripGitSuffix(parts[1])}`};
  }
  if (parts.length !== 3) throw new Error("azure_provider_coordinates_invalid");
  return {
    provider,
    repository: stripGitSuffix(parts[2]),
    provider_organization: parts[0],
    provider_project: parts[1],
  };
}

export function normalizeRepositorySelection(
  selectedProvider: RepositoryProvider,
  value: string,
): NormalizedRepositorySelection {
  const url = absoluteRepositoryUrl(value);
  if (!url) return normalizeShorthand(selectedProvider, value);

  const detected = detectRepositoryProvider(value);
  if (!detected) throw new Error("provider_repository_host_not_supported");
  if (detected !== selectedProvider) throw new Error("provider_repository_selection_mismatch");

  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  const parts = pathSegments(url);
  if (selectedProvider === "github") {
    if (host !== "github.com" || parts.length !== 2) throw new Error("github_repository_url_invalid");
    return normalizeShorthand(selectedProvider, `${parts[0]}/${stripGitSuffix(parts[1])}`);
  }
  if (selectedProvider === "gitlab") {
    if (host !== "gitlab.com" || parts.length < 2 || parts.includes("-")) throw new Error("gitlab_repository_url_invalid");
    return normalizeShorthand(selectedProvider, parts.map((part, index) => index === parts.length - 1 ? stripGitSuffix(part) : part).join("/"));
  }
  if (selectedProvider === "bitbucket_cloud") {
    if (host !== "bitbucket.org" || parts.length !== 2) throw new Error("bitbucket_repository_url_invalid");
    return normalizeShorthand(selectedProvider, `${parts[0]}/${stripGitSuffix(parts[1])}`);
  }

  if (host === "dev.azure.com") {
    if (parts.length !== 4 || parts[2].toLowerCase() !== "_git") throw new Error("azure_repository_url_invalid");
    return normalizeShorthand(selectedProvider, `${parts[0]}/${parts[1]}/${stripGitSuffix(parts[3])}`);
  }
  const visualStudio = host.match(/^([a-z0-9.-]+)\.visualstudio\.com$/i);
  if (!visualStudio || parts.length !== 3 || parts[1].toLowerCase() !== "_git") {
    throw new Error("azure_repository_url_invalid");
  }
  return normalizeShorthand(selectedProvider, `${visualStudio[1]}/${parts[0]}/${stripGitSuffix(parts[2])}`);
}

export function readRepositoryProvider(): RepositoryProvider {
  if (typeof window === "undefined") return "github";
  const value = window.sessionStorage.getItem(REPOSITORY_PROVIDER_STORAGE_KEY);
  return REPOSITORY_PROVIDER_OPTIONS.some((option) => option.value === value)
    ? value as RepositoryProvider
    : "github";
}

export function writeRepositoryProvider(provider: RepositoryProvider): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(REPOSITORY_PROVIDER_STORAGE_KEY, provider);
}

export function readOperatorAdminToken(): string {
  if (typeof window === "undefined") return "";
  return String(window.sessionStorage.getItem(OPERATOR_ADMIN_TOKEN_STORAGE_KEY) || "").trim();
}

export function writeOperatorAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  const normalized = token.trim();
  if (normalized) window.sessionStorage.setItem(OPERATOR_ADMIN_TOKEN_STORAGE_KEY, normalized);
  else window.sessionStorage.removeItem(OPERATOR_ADMIN_TOKEN_STORAGE_KEY);
}

export function providerOption(provider: RepositoryProvider): RepositoryProviderOption {
  return REPOSITORY_PROVIDER_OPTIONS.find((option) => option.value === provider) || REPOSITORY_PROVIDER_OPTIONS[0];
}
