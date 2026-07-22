"use client";

import {useEffect} from "react";

export default function SpanishDocumentLanguage() {
  useEffect(() => {
    const previous = document.documentElement.lang;
    document.documentElement.lang = "es-MX";
    document.body.dataset.nicoLocale = "es-MX";
    return () => {
      document.documentElement.lang = previous || "en";
      delete document.body.dataset.nicoLocale;
    };
  }, []);

  return null;
}
