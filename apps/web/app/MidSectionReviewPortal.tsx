"use client";

import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import MidSectionReview from "./assessment/MidSectionReview";

const MID_RESPONSE_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run(?:\/[^/]+\/status)?$/;
const TIER_EVENT = "nico:assessment-tier-selected";
const MOUNT_ID = "nico-mid-section-review-mount";
const REPLACED_ATTRIBUTE = "data-nico-mid-section-grid-replaced";

type JsonRecord = Record<string, unknown>;
type Section = Parameters<typeof MidSectionReview>[0]["sections"];

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

function restoreOriginalGrids() {
  document.querySelectorAll<HTMLElement>(`[${REPLACED_ATTRIBUTE}="true"]`).forEach((grid) => {
    grid.hidden = false;
    grid.removeAttribute(REPLACED_ATTRIBUTE);
  });
}

function findOrCreateMount(): HTMLElement | null {
  if (window.location.pathname !== "/assessment") return null;
  const resultPanel = document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!resultPanel) return null;
  const originalGrid = resultPanel.querySelector<HTMLElement>(".results-grid");
  if (!originalGrid) return null;

  originalGrid.hidden = true;
  originalGrid.setAttribute(REPLACED_ATTRIBUTE, "true");

  const existing = document.getElementById(MOUNT_ID);
  if (existing) {
    if (existing.nextElementSibling !== originalGrid) originalGrid.insertAdjacentElement("beforebegin", existing);
    return existing;
  }

  const mount = document.createElement("div");
  mount.id = MOUNT_ID;
  mount.setAttribute("data-nico-mid-section-review", "true");
  originalGrid.insertAdjacentElement("beforebegin", mount);
  return mount;
}

export default function MidSectionReviewPortal() {
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
      if (!isMid) {
        setPayload(null);
        setMount(null);
        document.getElementById(MOUNT_ID)?.remove();
        restoreOriginalGrids();
      }
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
      restoreOriginalGrids();
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
    restoreOriginalGrids();
  }, []);

  if (!midSelected || !payload || !mount) return null;
  const assessment = isRecord(payload.assessment) ? payload.assessment : null;
  const sections = Array.isArray(assessment?.sections) ? assessment.sections as Section : [];
  if (!sections.length) return null;

  return createPortal(<MidSectionReview sections={sections} />, mount);
}
