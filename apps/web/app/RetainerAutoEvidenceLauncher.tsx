"use client";

import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import {usePathname} from "next/navigation";

export default function RetainerAutoEvidenceLauncher() {
  const pathname = usePathname();
  const [target, setTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (pathname !== "/") {
      setTarget(null);
      return;
    }
    const section = document.querySelector<HTMLElement>("#retainer");
    if (!section) return;
    const legacyForm = section.querySelector<HTMLElement>(".command-card");
    const legacyButton = Array.from(section.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent?.includes("Run Retainer Ops"));
    if (legacyForm) legacyForm.hidden = true;
    if (legacyButton) legacyButton.hidden = true;
    section.dataset.retainerEvidenceMode = "automatic";
    setTarget(section);
    return () => {
      if (legacyForm) legacyForm.hidden = false;
      if (legacyButton) legacyButton.hidden = false;
      delete section.dataset.retainerEvidenceMode;
      setTarget(null);
    };
  }, [pathname]);

  if (!target) return null;
  return createPortal(
    <div className="inset-grid" data-retainer-auto-evidence-launcher="true">
      <p className="summary-box"><b>Automatic evidence mode:</b> commits, pull requests, issues, workflows, CodeQL runs, releases, and deployments are collected from the authorized repository. Only roadmap, client, metric, budget, and priority context remains operator-supplied.</p>
      <p className="warning-box">An empty field never proves a clean result. Blockers show clear only after the required GitHub sources are successfully checked.</p>
      <div className="report-actions"><a className="primary-link" href="/retainer-ops">Open Retainer Evidence Run</a></div>
    </div>,
    target,
  );
}
