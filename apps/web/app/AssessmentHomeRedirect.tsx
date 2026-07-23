"use client";

import {useLayoutEffect} from "react";
import {usePathname} from "next/navigation";

export default function AssessmentHomeRedirect() {
  const pathname = usePathname();

  useLayoutEffect(() => {
    if (pathname !== "/") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("legacy") === "1") return;
    window.location.replace("/assessment?tier=express#assessment");
  }, [pathname]);

  if (pathname !== "/") return null;
  return <div className="nico-home-redirect" role="status" aria-live="polite">
    <b>NICO</b>
    <span>Opening the assessment workspace…</span>
  </div>;
}
