"use client";

import {useEffect} from "react";

const MID_RESPONSE_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run(?:\/[^/]+\/status)?$/;
const MID_PAYLOAD_EVENT = "nico:mid-status-payload";

type JsonRecord = Record<string, unknown>;

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.origin);
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function publishMidPayload(payload: JsonRecord) {
  window.dispatchEvent(new CustomEvent<JsonRecord>(MID_PAYLOAD_EVENT, {detail: payload}));
}

export default function MidScoreIntelligencePortal() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const captureFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const url = requestUrl(input);
      if (url && MID_RESPONSE_PATH.test(url.pathname) && response.ok) {
        try {
          const parsed = await response.clone().json();
          if (isRecord(parsed) && String(parsed.assessment_type || parsed.service_tier || "mid") === "mid") {
            publishMidPayload(parsed);
          }
        } catch {
          // The assessment page remains authoritative when a response is not JSON.
        }
      }
      return response;
    };
    window.fetch = captureFetch;
    return () => {
      if (window.fetch === captureFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
