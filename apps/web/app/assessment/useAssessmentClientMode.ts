"use client";

import {useEffect, useState} from "react";

export type AssessmentClientMode = {
  hydrated: boolean;
  compactMobile: boolean;
};

const QUERY = "(max-width: 1024px), (pointer: coarse)";

export function useAssessmentClientMode(): AssessmentClientMode {
  // Fail closed for the server render and first client paint. A phone must never
  // allocate the desktop assessment tree before its device class is known.
  const [mode, setMode] = useState<AssessmentClientMode>({
    hydrated: false,
    compactMobile: true,
  });

  useEffect(() => {
    const query = window.matchMedia(QUERY);
    const synchronize = () => setMode({hydrated: true, compactMobile: query.matches});
    synchronize();
    query.addEventListener?.("change", synchronize);
    return () => query.removeEventListener?.("change", synchronize);
  }, []);

  return mode;
}
