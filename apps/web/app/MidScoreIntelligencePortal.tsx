"use client";

import type {ComponentProps} from "react";
import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import MidScoreIntelligence from "./assessment/MidScoreIntelligence";

const MID_RESPONSE_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run(?:\/[^/]+\/status)?$/;
const TIER_EVENT = "nico:assessment-tier-selected";
const MID_PAYLOAD_EVENT = "nico:mid-status-payload";
const MOUNT_ID = "nico-mid-score-intelligence-mount";

type JsonRecord = Record<string, unknown>;
type IntelligenceProps = ComponentProps<typeof MidScoreIntelligence>;

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

function findOrCreateMount(): HTMLElement | null {
  if (window.location.pathname !== "/assessment") return null;
  const existing = document.getElementById(MOUNT_ID);
  if (existing) return existing;
  const resultPanel = document.querySelector('section[aria-live="polite"]');
  if (!resultPanel) return null;
  const targetGrids = resultPanel.querySelectorAll(".target-grid");
  if (!targetGrids.length) return null;
  const mount = document.createElement("div");
  mount.id = MOUNT_ID;
  mount.setAttribute("data-nico-mid-score-intelligence", "true");
  const anchor = targetGrids[targetGrids.length - 1];
  anchor.insertAdjacentElement("afterend", mount);
  return mount;
}

export default function MidScoreIntelligencePortal() {
  const [payload, setPayload] = useState<JsonRecord | null>(null);
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const [midSelected, setMidSelected] = useState(false);

  useEffect(() => {
    const selected = new URLSearchParams(window.location.search).get("tier") === "mid";
    setMidSelected(selected);
    const onTier = (event: Event) => {
      const detail = (event as CustomEvent<{tier?: string}>).detail || {};
      const isMid = detail.tier === "mid";
      setMidSelected(isMid);
      if (!isMid) setPayload(null);
    };
    window.addEventListener(TIER_EVENT, onTier);
    return () => window.removeEventListener(TIER_EVENT, onTier);
  }, []);

  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const captureFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const url = requestUrl(input);
      if (url && MID_RESPONSE_PATH.test(url.pathname) && response.ok) {
        try {
          const parsed = await response.clone().json();
          if (isRecord(parsed) && String(parsed.assessment_type || parsed.service_tier || "mid") === "mid") {
            setPayload(parsed);
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

  useEffect(() => {
    if (!midSelected || !payload) {
      setMount(null);
      return;
    }
    const refresh = () => setMount(findOrCreateMount());
    refresh();
    const observer = new MutationObserver(refresh);
    observer.observe(document.body, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, [midSelected, payload]);

  useEffect(() => () => {
    document.getElementById(MOUNT_ID)?.remove();
  }, []);

  if (!midSelected || !payload || !mount) return null;
  const assessment = isRecord(payload.assessment) ? payload.assessment : null;
  const intelligenceResult = payload as unknown as IntelligenceProps["result"];
  const intelligenceDocument = assessment as unknown as IntelligenceProps["document"];
  return createPortal(
    <MidScoreIntelligence result={intelligenceResult} document={intelligenceDocument} />,
    mount,
  );
}
