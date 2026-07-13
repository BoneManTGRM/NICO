"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

export default function AssessmentHomeRedirect() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname !== "/") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("legacy") === "1") return;
    window.location.replace("/assessment?tier=express#assessment");
  }, [pathname]);

  return null;
}
