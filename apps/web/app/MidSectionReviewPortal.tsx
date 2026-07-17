"use client";

import {useEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import MidSectionReview from "./assessment/MidSectionReview";

const TIER_EVENT = "nico:assessment-tier-selected";
const MID_PAYLOAD_EVENT = "nico:mid-status-payload";
const MOUNT_ID = "nico-mid-unified-review-mount";
const LEGACY_ATTRIBUTE = "data-nico-mid-legacy-hidden";
const DURABLE_ARRAY_KEYS = new Set([
  "sections",
  "weighted_sections",
  "evidence",
  "findings",
  "unavailable",
  "missing_evidence_sources",
  "failed_evidence_tools",
  "scope_disclosures",
]);
const DURABLE_SCALAR_KEYS = new Set([
  "pdf_base64",
  "pdf",
  "markdown",
  "html",
  "pdf_filename",
  "pdf_sha256",
  "report_id",
  "run_id",
  "repository",
  "technical_score",
  "evidence_readiness",
  "evidence_readiness_score",
  "final_report_score",
  "reported_score",
  "calculated_score",
  "score",
]);
const MONOTONIC_TRUE_KEYS = new Set([
  "pdf_available",
  "markdown_available",
  "html_available",
  "pdf_integrity_verified",
  "report_artifact_rehydrated",
  "score_match",
]);
const MONOTONIC_STATUS_KEYS = new Set([
  "report_generation_status",
  "draft_generation_status",
  "human_review_status",
  "approval_request_status",
]);
const MONOTONIC_STATUS_PARENTS = new Set([
  "approval_request",
  "report_artifact_status",
  "mid_report",
]);

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assessmentSections(payload: JsonRecord | null): unknown[] {
  const assessment = payload && isRecord(payload.assessment) ? payload.assessment : null;
  return assessment && Array.isArray(assessment.sections) ? assessment.sections : [];
}

function payloadRunId(payload: JsonRecord | null): string {
  if (!payload) return "";
  const assessment = isRecord(payload.assessment) ? payload.assessment : {};
  return String(payload.run_id || assessment.run_id || "").trim();
}

function isMeaningful(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return true;
}

function normalizedStatus(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function statusRank(value: unknown): number {
  const status = normalizedStatus(value);
  if (!status) return 0;
  if (["queued", "pending", "not_started", "requested", "waiting"].includes(status)) return 1;
  if (["running", "in_progress", "generating", "processing"].includes(status)) return 2;
  if (["blocked", "cancelled", "declined", "error", "failed", "rejected"].includes(status)) return 3;
  if (["available", "complete", "completed", "generated", "ready", "success", "succeeded"].includes(status)) return 4;
  if (["accepted", "approved"].includes(status)) return 5;
  return 0;
}

function isMonotonicStatusPath(path: string[]): boolean {
  const key = path[path.length - 1] || "";
  if (MONOTONIC_STATUS_KEYS.has(key)) return true;
  const parent = path[path.length - 2] || "";
  return key === "status" && MONOTONIC_STATUS_PARENTS.has(parent);
}

function mergePayloadRecord(previous: JsonRecord, incoming: JsonRecord, path: string[] = []): JsonRecord {
  const output: JsonRecord = {...previous};
  for (const [key, incomingValue] of Object.entries(incoming)) {
    const previousValue = previous[key];
    const nextPath = [...path, key];
    if (isRecord(previousValue) && isRecord(incomingValue)) {
      output[key] = mergePayloadRecord(previousValue, incomingValue, nextPath);
      continue;
    }
    if (Array.isArray(incomingValue)) {
      output[key] = incomingValue.length || !DURABLE_ARRAY_KEYS.has(key) || !Array.isArray(previousValue)
        ? incomingValue
        : previousValue;
      continue;
    }
    if (MONOTONIC_TRUE_KEYS.has(key) && previousValue === true && incomingValue !== true) {
      output[key] = previousValue;
      continue;
    }
    if (isMonotonicStatusPath(nextPath) && statusRank(previousValue) > statusRank(incomingValue)) {
      output[key] = previousValue;
      continue;
    }
    if (DURABLE_SCALAR_KEYS.has(key) && !isMeaningful(incomingValue) && isMeaningful(previousValue)) {
      output[key] = previousValue;
      continue;
    }
    output[key] = incomingValue;
  }
  return output;
}

function mergeMidPayload(previous: JsonRecord | null, incoming: JsonRecord): JsonRecord {
  if (!previous) return incoming;
  const previousRunId = payloadRunId(previous);
  const incomingRunId = payloadRunId(incoming);
  if (previousRunId && incomingRunId && previousRunId !== incomingRunId) return incoming;
  return mergePayloadRecord(previous, incoming);
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
  const midSelectedRef = useRef(false);

  useEffect(() => {
    const applyTier = (isMid: boolean) => {
      midSelectedRef.current = isMid;
      setMidSelected(isMid);
      if (!isMid) {
        setPayload(null);
        setMount(null);
        document.getElementById(MOUNT_ID)?.remove();
        restoreLegacySurface();
      }
    };
    const syncFromLocation = () => applyTier(new URLSearchParams(window.location.search).get("tier") === "mid");
    syncFromLocation();
    const onTier = (event: Event) => {
      const detail = (event as CustomEvent<{tier?: string}>).detail || {};
      applyTier(detail.tier === "mid");
    };
    window.addEventListener(TIER_EVENT, onTier);
    window.addEventListener("popstate", syncFromLocation);
    return () => {
      window.removeEventListener(TIER_EVENT, onTier);
      window.removeEventListener("popstate", syncFromLocation);
    };
  }, []);

  useEffect(() => {
    const onPayload = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (!midSelectedRef.current) return;
      if (isRecord(detail) && String(detail.assessment_type || detail.service_tier || "mid") === "mid") {
        setPayload((current) => mergeMidPayload(current, detail));
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
