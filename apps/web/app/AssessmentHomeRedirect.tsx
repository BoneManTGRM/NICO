"use client";

import {useLayoutEffect} from "react";
import {usePathname} from "next/navigation";

export default function AssessmentHomeRedirect() {
  const pathname = usePathname();

  useLayoutEffect(() => {
    if (pathname !== "/") return;
    window.location.replace("/assessment?tier=comprehensive#assessment");
  }, [pathname]);

  if (pathname !== "/") return null;
  return <div className="nico-home-redirect" role="status" aria-live="polite">
    <b>NICO</b>
    <span>Opening NICO Comprehensive…</span>
  </div>;
}
