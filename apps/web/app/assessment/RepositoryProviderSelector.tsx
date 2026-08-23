"use client";

import {useEffect, useState} from "react";
import styles from "./repositoryProviderSelector.module.css";
import {
  detectRepositoryProvider,
  providerOption,
  readOperatorAdminToken,
  readRepositoryProvider,
  REPOSITORY_PROVIDER_OPTIONS,
  type RepositoryProvider,
  writeOperatorAdminToken,
  writeRepositoryProvider,
} from "./repositoryProvider";
import type {Locale} from "./assessmentTypes";

type Props = {
  locale: Locale;
  repository: string;
  setRepository: (value: string) => void;
  running: boolean;
};

export default function RepositoryProviderSelector({locale, repository, setRepository, running}: Props) {
  const spanish = locale === "es-MX";
  const [provider, setProvider] = useState<RepositoryProvider>("github");
  const [operatorToken, setOperatorToken] = useState("");

  useEffect(() => {
    setProvider(readRepositoryProvider());
    setOperatorToken(readOperatorAdminToken());
  }, []);

  useEffect(() => {
    const detected = detectRepositoryProvider(repository);
    if (detected && detected !== provider) {
      setProvider(detected);
      writeRepositoryProvider(detected);
    }
  }, [repository, provider]);

  function selectProvider(value: RepositoryProvider) {
    setProvider(value);
    writeRepositoryProvider(value);
  }

  function updateOperatorToken(value: string) {
    setOperatorToken(value);
    writeOperatorAdminToken(value);
  }

  const selected = providerOption(provider);
  return <div className={styles.providerBlock} data-repository-provider={provider}>
    <label className={styles.providerField}>
      {spanish ? "Proveedor del repositorio" : "Repository provider"}
      <select
        value={provider}
        onChange={(event) => selectProvider(event.target.value as RepositoryProvider)}
        disabled={running}
        aria-label={spanish ? "Proveedor del repositorio" : "Repository provider"}
      >
        {REPOSITORY_PROVIDER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <span className={styles.hint}>
        {spanish
          ? "También puedes pegar una URL HTTPS completa; NICO reconocerá el proveedor por el host exacto."
          : "You can also paste a complete HTTPS URL; NICO will recognize the provider from the exact host."}
      </span>
    </label>

    <label className={styles.repositoryField}>
      {spanish ? "URL o identificador del repositorio" : "Repository URL or identifier"}
      <input
        value={repository}
        onChange={(event) => setRepository(event.target.value)}
        placeholder={selected.placeholder}
        disabled={running}
        autoComplete="off"
        spellCheck={false}
      />
      <span className={styles.hint}>{selected.label} · {selected.placeholder}</span>
    </label>

    {provider !== "github" ? <div className={styles.operatorPanel}>
      <label className={styles.operatorField}>
        {spanish ? "Autorización del operador NICO" : "NICO operator authorization"}
        <input
          type="password"
          value={operatorToken}
          onChange={(event) => updateOperatorToken(event.target.value)}
          placeholder={spanish ? "Token de operador requerido" : "Operator token required"}
          disabled={running}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <p className={styles.operatorNote}>
        {spanish
          ? "Se conserva únicamente durante esta sesión del navegador. Las credenciales de GitLab, Bitbucket y Azure permanecen exclusivamente en el servidor."
          : "Kept only for this browser session. GitLab, Bitbucket, and Azure provider credentials remain server-side only."}
      </p>
    </div> : null}
  </div>;
}
