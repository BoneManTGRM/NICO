"use client";

import {useEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import styles from "./repositoryProviderSelector.module.css";
import {
  detectRepositoryProvider,
  normalizeRepositorySelection,
  providerOption,
  readOperatorAdminToken,
  readRepositoryProvider,
  REPOSITORY_PROVIDER_OPTIONS,
  type RepositoryProvider,
  writeOperatorAdminToken,
  writeRepositoryProvider,
} from "./repositoryProvider";
import type {Locale} from "./assessmentTypes";

const PUBLIC_INTAKE_PATH = "/api/nico/assessment/comprehensive-intake";
const OPERATOR_INTAKE_PATH = "/api/nico/providers/operator/comprehensive-intake";
const PROVIDER_MOUNT_ATTRIBUTE = "data-nico-repository-provider-mount";

function errorResponse(status: number, code: string, message: string): Response {
  return Response.json(
    {status: "error", detail: {code, message, retryable: false}},
    {status, headers: {"Cache-Control": "no-store"}},
  );
}

function exactPath(input: RequestInfo | URL): string {
  try {
    if (input instanceof Request) return new URL(input.url, window.location.origin).pathname;
    return new URL(String(input), window.location.origin).pathname;
  } catch {
    return "";
  }
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
}

async function requestBodyText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  if (typeof init?.body === "string") return init.body;
  if (input instanceof Request) return input.clone().text();
  return "";
}

function requestHeaders(input: RequestInfo | URL, init?: RequestInit): Headers {
  const headers = new Headers(input instanceof Request ? input.headers : undefined);
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
  return headers;
}

function repositoryFieldLabel(locale: Locale): string {
  return locale === "es-MX" ? "URL o identificador del repositorio" : "Repository URL or identifier";
}

function operatorMessage(locale: Locale): string {
  return locale === "es-MX"
    ? "Se requiere la autorización del operador NICO para usar GitLab, Bitbucket o Azure DevOps."
    : "NICO operator authorization is required for GitLab, Bitbucket, or Azure DevOps.";
}

export default function AssessmentProviderParityBridge({locale}: {locale: Locale}) {
  const [provider, setProvider] = useState<RepositoryProvider>("github");
  const [operatorToken, setOperatorToken] = useState("");
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const repositoryInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setProvider(readRepositoryProvider());
    setOperatorToken(readOperatorAdminToken());
  }, []);

  useEffect(() => {
    writeRepositoryProvider(provider);
    const input = repositoryInput.current;
    if (input) input.placeholder = providerOption(provider).placeholder;
  }, [provider]);

  useEffect(() => {
    let observer: MutationObserver | null = null;
    let boundLabel: HTMLLabelElement | null = null;
    let boundInput: HTMLInputElement | null = null;
    let mountNode: HTMLDivElement | null = null;
    let originalLabelText = "";
    let originalPlaceholder = "";

    const bind = () => {
      if (boundInput?.isConnected) return true;
      const labels = Array.from(document.querySelectorAll<HTMLLabelElement>("label"));
      const label = labels.find((candidate) => {
        const text = String(candidate.textContent || "").trim().toLowerCase();
        const input = candidate.querySelector<HTMLInputElement>('input[autocomplete="off"]');
        return Boolean(input) && (
          text.startsWith("repository owner/name or github url") ||
          text.startsWith("propietario/nombre del repositorio o url de github") ||
          text.startsWith("repository url or identifier") ||
          text.startsWith("url o identificador del repositorio")
        );
      });
      const input = label?.querySelector<HTMLInputElement>('input[autocomplete="off"]');
      if (!label || !input || !label.parentElement) return false;

      boundLabel = label;
      boundInput = input;
      repositoryInput.current = input;
      originalPlaceholder = input.placeholder;
      const firstText = Array.from(label.childNodes).find((node) => node.nodeType === Node.TEXT_NODE) as Text | undefined;
      if (firstText) {
        originalLabelText = firstText.nodeValue || "";
        firstText.nodeValue = repositoryFieldLabel(locale);
      }
      input.placeholder = providerOption(readRepositoryProvider()).placeholder;

      const onRepositoryInput = () => {
        const detected = detectRepositoryProvider(input.value);
        if (detected) {
          setProvider(detected);
          writeRepositoryProvider(detected);
        }
        window.requestAnimationFrame(() => {
          if (input.isConnected) input.placeholder = providerOption(detected || readRepositoryProvider()).placeholder;
        });
      };
      input.addEventListener("input", onRepositoryInput);
      input.addEventListener("change", onRepositoryInput);

      mountNode = document.createElement("div");
      mountNode.setAttribute(PROVIDER_MOUNT_ATTRIBUTE, "true");
      label.parentElement.insertBefore(mountNode, label);
      setMount(mountNode);

      const cleanup = () => {
        input.removeEventListener("input", onRepositoryInput);
        input.removeEventListener("change", onRepositoryInput);
      };
      (mountNode as HTMLDivElement & {__nicoCleanup?: () => void}).__nicoCleanup = cleanup;
      return true;
    };

    if (!bind()) {
      observer = new MutationObserver(() => {
        if (bind()) observer?.disconnect();
      });
      observer.observe(document.body, {subtree: true, childList: true});
    }

    return () => {
      observer?.disconnect();
      const cleanup = (mountNode as (HTMLDivElement & {__nicoCleanup?: () => void}) | null)?.__nicoCleanup;
      cleanup?.();
      if (boundLabel) {
        const firstText = Array.from(boundLabel.childNodes).find((node) => node.nodeType === Node.TEXT_NODE) as Text | undefined;
        if (firstText && originalLabelText) firstText.nodeValue = originalLabelText;
      }
      if (boundInput) boundInput.placeholder = originalPlaceholder;
      mountNode?.remove();
      repositoryInput.current = null;
      setMount(null);
    };
  }, [locale]);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const bridgedFetch: typeof window.fetch = async (input, init) => {
      if (requestMethod(input, init) !== "POST" || exactPath(input) !== PUBLIC_INTAKE_PATH) {
        return originalFetch(input, init);
      }

      const rawBody = await requestBodyText(input, init);
      let payload: Record<string, unknown>;
      try {
        const parsed = JSON.parse(rawBody || "{}");
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
        payload = parsed as Record<string, unknown>;
      } catch {
        return errorResponse(422, "assessment_intake_body_invalid_json", "The assessment intake body is not valid JSON.");
      }

      const repository = String(payload.repository || "").trim();
      const selectedProvider = detectRepositoryProvider(repository) || readRepositoryProvider();
      if (selectedProvider === "github") return originalFetch(input, init);

      const token = readOperatorAdminToken();
      if (!token) return errorResponse(403, "authorized_nico_operator_required", operatorMessage(locale));

      let normalized;
      try {
        normalized = normalizeRepositorySelection(selectedProvider, repository);
      } catch (error) {
        return errorResponse(
          422,
          error instanceof Error ? error.message : "provider_repository_invalid",
          locale === "es-MX"
            ? "La URL o el identificador del repositorio no coincide con el proveedor seleccionado."
            : "The repository URL or identifier does not match the selected provider.",
        );
      }

      const headers = requestHeaders(input, init);
      headers.set("Content-Type", "application/json");
      headers.set("X-NICO-Admin-Token", token);
      const nextBody: Record<string, unknown> = {
        ...payload,
        provider: normalized.provider,
        repository: normalized.repository,
        authorized_by: "nico_operator_ui",
      };
      if (normalized.provider_organization) nextBody.provider_organization = normalized.provider_organization;
      if (normalized.provider_project) nextBody.provider_project = normalized.provider_project;

      return originalFetch(
        new URL(OPERATOR_INTAKE_PATH, window.location.origin).href,
        {
          ...init,
          method: "POST",
          headers,
          body: JSON.stringify(nextBody),
          cache: "no-store",
        },
      );
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = originalFetch;
    };
  }, [locale]);

  function selectProvider(value: RepositoryProvider) {
    setProvider(value);
    writeRepositoryProvider(value);
  }

  function updateOperatorToken(value: string) {
    setOperatorToken(value);
    writeOperatorAdminToken(value);
  }

  if (!mount) return null;
  return createPortal(
    <div className={styles.providerBlock} data-repository-provider={provider} data-no-localize="true">
      <label className={styles.providerField}>
        {locale === "es-MX" ? "Proveedor del repositorio" : "Repository provider"}
        <select
          value={provider}
          onChange={(event) => selectProvider(event.target.value as RepositoryProvider)}
          aria-label={locale === "es-MX" ? "Proveedor del repositorio" : "Repository provider"}
        >
          {REPOSITORY_PROVIDER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <span className={styles.hint}>
          {locale === "es-MX"
            ? "Selecciona el proveedor o pega una URL HTTPS completa para detectarlo por el host exacto."
            : "Select the provider or paste a complete HTTPS URL to detect it from the exact host."}
        </span>
      </label>
      {provider !== "github" ? <div className={styles.operatorPanel}>
        <label className={styles.operatorField}>
          {locale === "es-MX" ? "Autorización del operador NICO" : "NICO operator authorization"}
          <input
            type="password"
            value={operatorToken}
            onChange={(event) => updateOperatorToken(event.target.value)}
            placeholder={locale === "es-MX" ? "Token de operador requerido" : "Operator token required"}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <p className={styles.operatorNote}>
          {locale === "es-MX"
            ? "El token de operador se conserva solo durante esta sesión. Las credenciales del proveedor permanecen exclusivamente en el servidor."
            : "The operator token is kept only for this session. Provider credentials remain server-side only."}
        </p>
      </div> : null}
    </div>,
    mount,
  );
}
