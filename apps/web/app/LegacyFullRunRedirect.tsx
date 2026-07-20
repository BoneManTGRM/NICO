"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

export default function LegacyFullRunRedirect() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname !== "/full-run") return;

    const params = new URLSearchParams(window.location.search);
    if (params.get("legacy") === "1" || params.get("review") === "1") return;

    window.location.replace("/assessment?tier=comprehensive#assessment");
  }, [pathname]);

  return null;
}
