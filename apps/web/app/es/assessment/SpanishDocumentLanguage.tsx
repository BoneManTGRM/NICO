"use client";

import {useEffect} from "react";

export default function SpanishDocumentLanguage() {
  useEffect(() => {
    const previousLanguage = document.documentElement.lang;
    const previousDirection = document.documentElement.dir;
    const previousHtmlLocale = document.documentElement.dataset.nicoLocale;
    const previousBodyLocale = document.body.dataset.nicoLocale;

    document.documentElement.lang = "es-MX";
    document.documentElement.dir = "ltr";
    document.documentElement.dataset.nicoLocale = "es-MX";
    document.body.dataset.nicoLocale = "es-MX";

    return () => {
      document.documentElement.lang = previousLanguage || "en";
      document.documentElement.dir = previousDirection || "ltr";
      if (previousHtmlLocale) document.documentElement.dataset.nicoLocale = previousHtmlLocale;
      else delete document.documentElement.dataset.nicoLocale;
      if (previousBodyLocale) document.body.dataset.nicoLocale = previousBodyLocale;
      else delete document.body.dataset.nicoLocale;
    };
  }, []);

  return null;
}
