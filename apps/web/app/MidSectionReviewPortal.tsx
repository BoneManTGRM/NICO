"use client";

import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import MidSectionReview from "./assessment/MidSectionReview";

const TIER_EVENT = "nico:assessment-tier-selected";
const MID_PAYLOAD_EVENT = "nico:mid-status-payload";
const MOUNT_ID = "nico-mid-section-review-mount";
const REPLACED_ATTRIBUTE = "data-nico-mid-section-grid-replaced";

type JsonRecord = Record<string, unknown>;
type ReviewSections = NonNullable<Parameters<typeof MidSectionReview>[0]["sections"]>;

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
    const onPayload = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (isRecord(detail) && String(detail.assessment_type || detail.service_tier || "mid") === "mid") {
        setPayload(detail);
      }
    };
    window.addEventListener(MID_PAYLOAD_EVENT, onPayload);
    return () => window.removeEventListener(MID_PAYLOAD_EVENT, onPayload);
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
  const sections: ReviewSections = Array.isArray(assessment?.sections) ? assessment.sections as ReviewSections : [];
  if (!sections.length) return null;

  return createPortal(<MidSectionReview sections={sections} />, mount);
}
