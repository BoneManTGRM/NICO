"use client";

import {useEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import styles from "./repositoryProviderSelector.module.css";
import {
  detectRepositoryProvider,
  providerPlaceholder,
  readRepositoryProvider,
  REPOSITORY_PROVIDER_OPTIONS,
  type RepositoryProvider,
  writeRepositoryProvider,
} from "./repositoryProvider";
import type {Locale} from "./assessmentTypes";

const PROVIDER_MOUNT_ATTRIBUTE = "data-nico-repository-provider-mount";

function repositoryFieldLabel(locale: Locale): string {
  return locale === "es-MX" ? "URL o identificador del repositorio" : "Repository URL or identifier";
}

export default function AssessmentProviderParityBridge({locale}: {locale: Locale}) {
  const [provider, setProvider] = useState<RepositoryProvider>("github");
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const repositoryInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setProvider(readRepositoryProvider());
  }, []);

  useEffect(() => {
    writeRepositoryProvider(provider);
    const input = repositoryInput.current;
    if (input) input.placeholder = providerPlaceholder(provider, locale);
  }, [provider, locale]);

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
      input.placeholder = providerPlaceholder(readRepositoryProvider(), locale);

      const onRepositoryInput = () => {
        const detected = detectRepositoryProvider(input.value);
        if (detected) {
          setProvider(detected);
          writeRepositoryProvider(detected);
        }
        window.requestAnimationFrame(() => {
          if (input.isConnected) {
            input.placeholder = providerPlaceholder(detected || readRepositoryProvider(), locale);
          }
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
    };
  }, [locale]);

  function selectProvider(value: RepositoryProvider) {
    setProvider(value);
    writeRepositoryProvider(value);
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
      <p className={styles.operatorNote}>
        {locale === "es-MX"
          ? "Los repositorios públicos se evalúan con acceso anónimo de solo lectura. Si el código fuente requerido no es público, NICO solicitará acceso de solo lectura por separado."
          : "Public repositories are assessed with anonymous read-only access. If required source code is not public, NICO will request read-only access separately."}
      </p>
    </div>,
    mount,
  );
}
