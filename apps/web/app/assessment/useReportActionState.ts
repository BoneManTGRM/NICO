"use client";

import {useEffect, useState} from "react";
import type {Locale} from "./assessmentTypes";
import {REPORT_LOCALE_CHANGE_EVENT, reportLanguageForRequest, persistReportLocale} from "./assessmentLocale";

export function useReportActionState(locale: Locale) {
  const [copied, setCopied] = useState(false);
  const [artifactAction, setArtifactAction] = useState<"markdown" | "pdf" | null>(null);
  const [requestedReportLanguage, setRequestedReportLanguage] = useState<ReturnType<typeof reportLanguageForRequest>>(
    reportLanguageForRequest(locale),
  );
  useEffect(() => {
    const syncRequestedReportLanguage = () => {
      setRequestedReportLanguage(reportLanguageForRequest(locale));
    };
    syncRequestedReportLanguage();
    window.addEventListener(REPORT_LOCALE_CHANGE_EVENT, syncRequestedReportLanguage);
    return () => window.removeEventListener(REPORT_LOCALE_CHANGE_EVENT, syncRequestedReportLanguage);
  }, [locale]);
  const [reportLocaleError, setReportLocaleError] = useState("");
  function chooseEnglishReport() {
    try {
      persistReportLocale("en-US");
      setReportLocaleError("");
    } catch {
      setReportLocaleError(locale === "es-MX"
        ? "No se pudo cambiar el idioma del informe porque el navegador rechazó la actualización de la dirección. Tu selección anterior se conserva."
        : "Could not change the report language because the browser rejected the address update. Your previous selection is unchanged.");
    }
  }

  return {copied, setCopied, artifactAction, setArtifactAction, requestedReportLanguage, reportLocaleError, chooseEnglishReport};
}
