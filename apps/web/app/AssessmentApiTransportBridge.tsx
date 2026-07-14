"use client";

import {useEffect} from "react";

const CONFIGURED_API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const ASSESSMENT_PATH = /^\/assessment\/(?:github|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

export default function AssessmentApiTransportBridge() {
  useEffect(() => {
    if (!CONFIGURED_API_URL) return;

    let configured: URL;
    try {
      configured = new URL(CONFIGURED_API_URL);
    } catch {
      return;
    }

    const configuredPath = configured.pathname.replace(/\/$/, "");
    const originalFetch = window.fetch.bind(window);

    const bridgedFetch: typeof window.fetch = (input, init) => {
      let requested: URL;
      try {
        requested = new URL(requestUrl(input), window.location.href);
      } catch {
        return originalFetch(input, init);
      }

      if (requested.origin !== configured.origin) return originalFetch(input, init);
      if (configuredPath && !requested.pathname.startsWith(`${configuredPath}/`)) return originalFetch(input, init);

      const apiPath = configuredPath ? requested.pathname.slice(configuredPath.length) : requested.pathname;
      if (!ASSESSMENT_PATH.test(apiPath)) return originalFetch(input, init);

      const proxyUrl = new URL(`/api/nico${apiPath}${requested.search}`, window.location.origin);
      if (input instanceof Request) {
        return originalFetch(new Request(proxyUrl, input), init);
      }
      return originalFetch(proxyUrl, init);
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
