"use client";

import {useEffect, useState} from "react";
import {createPortal} from "react-dom";
import MidSectionReview from "./assessment/MidSectionReview";

const TIER_EVENT = "nico:assessment-tier-selected";
const MID_PAYLOAD_EVENT = "nico:mid-status-payload";
const MOUNT_ID = "nico-mid-unified-review-mount";
const LEGACY_ATTRIBUTE = "data-nico-mid-legacy-hidden";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assessmentSections(payload: JsonRecord | null): unknown[] {
  const assessment = payload && isRecord(payload.assessment) ? payload.assessment : null;
  return assessment && Array.isArray(assessment.sections) ? assessment.sections : [];
}

function restoreLegacySurface() {
  document.querySelectorAll<HTMLElement>(`[${LEGACY_ATTRIBUTE}="true"]`).forEach((element) => {
    element.hidden = false;
    element.removeAttribute(LEGACY_ATTRIBUTE);
  });
}

function hideLegacySurface(panel: HTMLElement, mount: HTMLElement) {
  Array.from(panel.children).forEach((child) => {
    if (!(child instanceof HTMLElement) || child === mount) return;
    child.hidden = true;
    child.setAttribute(LEGACY_ATTRIBUTE, "true");
  });
}

function findOrCreateMount(): HTMLElement | null {
  if (window.location.pathname !== "/assessment") return null;
  const panel = document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!panel) return null;

  let mount = document.getElementById(MOUNT_ID);
  if (!mount) {
    mount = document.createElement("div");
    mount.id = MOUNT_ID;
    mount.setAttribute("data-nico-mid-unified-review", "true");
    panel.prepend(mount);
  } else if (mount.parentElement !== panel) {
    panel.prepend(mount);
  }
  hideLegacySurface(panel, mount);
  return mount;
}

export default function MidSectionReviewPortal() {
  const [payload, setPayload] = useState<JsonRecord | null>(null);
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const [midSelected, setMidSelected] = useState(false);

  useEffect(() => {
    setMidSelected(new URLSearchParams(window.location.search).get("tier") === "mid");
    const onTier = (event: Event) => {
      const detail = (event as CustomEvent<{tier?: string}>).detail || {};
      const isMid = detail.tier === "mid";
      setMidSelected(isMid);
      if (!isMid) {
        setPayload(null);
        setMount(null);
        document.getElementById(MOUNT_ID)?.remove();
        restoreLegacySurface();
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
        setMidSelected(true);
      }
    };
    window.addEventListener(MID_PAYLOAD_EVENT, onPayload);
    return () => window.removeEventListener(MID_PAYLOAD_EVENT, onPayload);
  }, []);

  useEffect(() => {
    if (!midSelected || !payload || !assessmentSections(payload).length) {
      setMount(null);
      restoreLegacySurface();
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
    restoreLegacySurface();
  }, []);

  if (!midSelected || !payload || !mount) return null;
  return createPortal(<MidSectionReview payload={payload} />, mount);
}
