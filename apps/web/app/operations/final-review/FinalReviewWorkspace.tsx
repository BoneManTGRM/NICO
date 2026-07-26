"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import styles from "./final-review.module.css";

const LEGACY_API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
type Service = "express" | "comprehensive";
type Decision = "request_more_evidence" | "rejected";
type Locale = "en" | "es-MX";
type JsonRecord = Record<string, unknown>;

type ReviewResponse = {
  status?: string;
  service?: Service;
  review_status?: string;
  acceptance_status?: string;
  approval_id?: string;
  client_delivery_allowed?: boolean;
  delivery_status?: string;
  approval?: JsonRecord;
  review?: JsonRecord;
  acceptance?: JsonRecord;
  approved_delivery?: JsonRecord;
  approved_delivery_package?: JsonRecord;
  approvals?: JsonRecord[];
  reports?: JsonRecord;
  accepted_edition?: JsonRecord;
  review_decision?: JsonRecord;
  review_context?: JsonRecord;
  record?: JsonRecord;
};

const COPY = {
  en: {
    eyebrow: "NICO CONTROLLED ACCEPTANCE",
    title: "Final review, without the friction.",
    lead: "Review the exact immutable Strategic report, confirm its evidence boundary, and authorize only the artifact set you actually examined.",
    assessment: "Assessment",
    exactRun: "Exact run",
    identity: "Identity",
    bound: "Bound",
    missing: "Missing",
    directRun: "Open this page from a completed assessment",
    secureAccess: "SECURE ACCESS",
    identifyReviewer: "Identify the authorized reviewer",
    identityAttached: "The report identity is already attached when this page is opened from a completed run.",
    reviewer: "Authorized reviewer",
    reviewerPlaceholder: "Full name or accountable identity",
    reviewerRole: "Reviewer role",
    reviewerRolePlaceholder: "Principal engineer, CTO, product owner…",
    operatorToken: "Operator admin token",
    secureToken: "Secure token",
    opening: "Opening review…",
    refresh: "Refresh review",
    open: "Open review",
    advanced: "Change report identity or scope",
    assessmentType: "Assessment type",
    exactRunId: "Exact run ID",
    customerId: "Customer ID",
    projectId: "Project ID",
    canonicalSecurity: "The reviewer identity and role are persisted in the approval certificate. The operator token stays only in this open page. No secret is stored in the URL or browser storage.",
    legacySecurity: "The operator token stays only in this open page. It is not written to the URL, browser storage, cookies, or build output.",
    enterReviewer: "Enter the exact run ID, operator token, authorized reviewer, and reviewer role.",
    enterLegacy: "Enter the operator token and authorized reviewer for this exact run.",
    loaded: "The immutable review package is loaded. Confirm it below when ready.",
    loadFailed: "Unable to load final review.",
    finalDecision: "FINAL DECISION",
    approveHeading: "Approve the exact accepted edition",
    approveLead: "One controlled action records the certificate and downloads the same PDF that was reviewed.",
    review: "Review",
    delivery: "Client delivery",
    authorized: "Authorized",
    blocked: "Blocked",
    waiting: "Waiting for secure access",
    emptyTitle: "Nothing else to complete yet.",
    emptyBody: "Identify the reviewer above, then open the exact review package.",
    reviewedExact: "I reviewed this exact report.",
    reviewedDetail: "I confirm the scorecard, evidence limitations, immutable run identity, artifact digest, and delivery boundary.",
    approvalNote: "Add approval context",
    approvalNoteLabel: "Decision context",
    approvalPlaceholder: "Optional approval context. A clear note is required for rejection or a request for more evidence.",
    recording: "Recording approval…",
    alreadyApproved: "Approval already recorded",
    approveDownload: "Approve and download final PDF",
    downloadAgain: "Download approved PDF again",
    downloadPackage: "Download approved delivery package",
    readyDelivery: "This exact immutable edition and its certified delivery package are approved for controlled client delivery.",
    blockedDelivery: "Delivery remains blocked until a valid approval certificate matches the current artifact set.",
    otherDecision: "Need a different decision?",
    otherDecisionLead: "Use these only when the package cannot be approved. A clear decision reason is required.",
    requestEvidence: "Request more evidence",
    reject: "Reject delivery",
    reportDigest: "Report artifact digest",
    certificateDigest: "Approval certificate",
    manifestDigest: "Accepted-edition manifest",
    packageDigest: "Delivery package digest",
    deliveryCertificateDigest: "Delivery authorization certificate",
    notIssued: "Not issued",
    technicalRecord: "Technical review record",
    confirmFirst: "Confirm that you reviewed the exact report and its disclosed limitations.",
    decisionNoteRequired: "Add a clear review note before requesting more evidence or rejecting delivery.",
    approvedNotice: "Approval recorded. The accepted final report was downloaded.",
    evidenceNotice: "More evidence requested. Delivery remains blocked. Start a new assessment with the requested evidence; this unchanged report cannot later be approved.",
    rejectedNotice: "Report rejected. Delivery remains blocked.",
    approvalFailed: "Unable to approve and download the final report.",
    decisionFailed: "Unable to record the review decision.",
    pdfMissing: "The reviewed response did not contain the exact PDF artifact.",
    invalidPdf: "The approved PDF failed browser integrity validation.",
    packageMissing: "The approved delivery package is unavailable for this exact run.",
    invalidPackage: "The approved delivery package failed ZIP integrity validation.",
    defaultApprovalReason: "Authorized reviewer confirmed the exact immutable report, scorecard, disclosed evidence limitations, artifact identity, and delivery boundary.",
  },
  "es-MX": {
    eyebrow: "ACEPTACIÓN CONTROLADA DE NICO",
    title: "Revisión final, sin fricción.",
    lead: "Revisa el informe Estratégico inmutable exacto, confirma su límite de evidencia y autoriza únicamente el conjunto de artefactos que examinaste.",
    assessment: "Evaluación",
    exactRun: "Ejecución exacta",
    identity: "Identidad",
    bound: "Vinculada",
    missing: "Faltante",
    directRun: "Abre esta página desde una evaluación terminada",
    secureAccess: "ACCESO SEGURO",
    identifyReviewer: "Identifica al revisor autorizado",
    identityAttached: "La identidad del informe ya está vinculada cuando esta página se abre desde una ejecución terminada.",
    reviewer: "Revisor autorizado",
    reviewerPlaceholder: "Nombre completo o identidad responsable",
    reviewerRole: "Función del revisor",
    reviewerRolePlaceholder: "Ingeniero principal, CTO, responsable del producto…",
    operatorToken: "Token de administrador del operador",
    secureToken: "Token seguro",
    opening: "Abriendo revisión…",
    refresh: "Actualizar revisión",
    open: "Abrir revisión",
    advanced: "Cambiar identidad o alcance del informe",
    assessmentType: "Tipo de evaluación",
    exactRunId: "ID de ejecución exacta",
    customerId: "ID del cliente",
    projectId: "ID del proyecto",
    canonicalSecurity: "La identidad y función del revisor se conservan en el certificado de aprobación. El token del operador permanece únicamente en esta página abierta. Ningún secreto se guarda en la URL ni en el almacenamiento del navegador.",
    legacySecurity: "El token del operador permanece únicamente en esta página abierta. No se escribe en la URL, almacenamiento, cookies ni compilación.",
    enterReviewer: "Ingresa el ID de ejecución exacta, el token del operador, el revisor autorizado y su función.",
    enterLegacy: "Ingresa el token del operador y el revisor autorizado para esta ejecución exacta.",
    loaded: "El paquete inmutable de revisión está cargado. Confírmalo abajo cuando estés listo.",
    loadFailed: "No fue posible cargar la revisión final.",
    finalDecision: "DECISIÓN FINAL",
    approveHeading: "Aprueba la edición aceptada exacta",
    approveLead: "Una acción controlada registra el certificado y descarga el mismo PDF que fue revisado.",
    review: "Revisión",
    delivery: "Entrega al cliente",
    authorized: "Autorizada",
    blocked: "Bloqueada",
    waiting: "Esperando acceso seguro",
    emptyTitle: "Todavía no hay nada más que completar.",
    emptyBody: "Identifica al revisor arriba y abre el paquete de revisión exacto.",
    reviewedExact: "Revisé este informe exacto.",
    reviewedDetail: "Confirmo la puntuación, las limitaciones de evidencia, la identidad inmutable, el hash del artefacto y el límite de entrega.",
    approvalNote: "Agregar contexto de aprobación",
    approvalNoteLabel: "Contexto de la decisión",
    approvalPlaceholder: "Contexto opcional de aprobación. Se requiere una nota clara para rechazar o solicitar más evidencia.",
    recording: "Registrando aprobación…",
    alreadyApproved: "Aprobación ya registrada",
    approveDownload: "Aprobar y descargar PDF final",
    downloadAgain: "Descargar nuevamente el PDF aprobado",
    downloadPackage: "Descargar paquete de entrega aprobado",
    readyDelivery: "Esta edición inmutable exacta y su paquete de entrega certificado están aprobados para entrega controlada al cliente.",
    blockedDelivery: "La entrega permanece bloqueada hasta que un certificado válido coincida con el conjunto actual de artefactos.",
    otherDecision: "¿Necesitas una decisión diferente?",
    otherDecisionLead: "Usa estas opciones únicamente cuando el paquete no pueda aprobarse. Se requiere una razón clara.",
    requestEvidence: "Solicitar más evidencia",
    reject: "Rechazar entrega",
    reportDigest: "Hash de artefactos del informe",
    certificateDigest: "Certificado de aprobación",
    manifestDigest: "Manifiesto de edición aceptada",
    packageDigest: "Hash del paquete de entrega",
    deliveryCertificateDigest: "Certificado de autorización de entrega",
    notIssued: "No emitido",
    technicalRecord: "Registro técnico de revisión",
    confirmFirst: "Confirma que revisaste el informe exacto y sus limitaciones declaradas.",
    decisionNoteRequired: "Agrega una nota clara antes de solicitar más evidencia o rechazar la entrega.",
    approvedNotice: "Aprobación registrada. Se descargó el informe final aceptado.",
    evidenceNotice: "Se solicitó más evidencia. La entrega permanece bloqueada. Inicia una nueva evaluación con la evidencia solicitada; este informe sin cambios no podrá aprobarse después.",
    rejectedNotice: "Informe rechazado. La entrega permanece bloqueada.",
    approvalFailed: "No fue posible aprobar y descargar el informe final.",
    decisionFailed: "No fue posible registrar la decisión de revisión.",
    pdfMissing: "La respuesta revisada no contiene el artefacto PDF exacto.",
    invalidPdf: "El PDF aprobado no superó la validación de integridad del navegador.",
    packageMissing: "El paquete de entrega aprobado no está disponible para esta ejecución exacta.",
    invalidPackage: "El paquete de entrega aprobado no superó la validación de integridad ZIP.",
    defaultApprovalReason: "El revisor autorizado confirmó el informe inmutable exacto, la puntuación, las limitaciones de evidencia declaradas, la identidad del artefacto y el límite de entrega.",
  },
} as const;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function approvedDeliveryFrom(value: ReviewResponse | null | undefined): JsonRecord {
  if (!value) return {};
  return asRecord(
    value.approved_delivery
      || asRecord(value.review).approved_delivery
      || asRecord(value.acceptance).approved_delivery,
  );
}

function approvedPackageFrom(value: ReviewResponse | null | undefined): JsonRecord {
  return asRecord(value?.approved_delivery_package);
}

function acceptedEditionFrom(value: ReviewResponse | null | undefined): JsonRecord {
  if (!value) return {};
  return asRecord(value.accepted_edition || value.review_decision);
}

function reviewCertificateFrom(value: ReviewResponse | null | undefined): JsonRecord {
  const edition = acceptedEditionFrom(value);
  return asRecord(edition.review || value?.review);
}

function reportFrom(value: ReviewResponse | null | undefined): JsonRecord {
  return asRecord(value?.reports);
}

function approvalIdFrom(value: ReviewResponse | null | undefined): string {
  if (!value) return "";
  const direct = String(value.approval_id || "");
  if (direct) return direct;
  const approval = asRecord(value.approval);
  if (approval.approval_id) return String(approval.approval_id);
  const first = Array.isArray(value.approvals) ? asRecord(value.approvals[0]) : {};
  return String(first.approval_id || "");
}

function mergeReviewResponses(latest: ReviewResponse, mutation: ReviewResponse): ReviewResponse {
  const mutationDelivery = approvedDeliveryFrom(mutation);
  const latestDelivery = approvedDeliveryFrom(latest);
  const merged: ReviewResponse = {...mutation, ...latest};
  if (Object.keys(mutationDelivery).length) merged.approved_delivery = {...latestDelivery, ...mutationDelivery};
  return merged;
}

function safeFilename(value: string, fallback: string): string {
  const normalized = value.replace(/[\r\n]/g, "").replace(/[\\/:*?\"<>|]/g, "-").trim();
  return normalized || fallback;
}

function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  const candidate = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    || disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]
    || "";
  try {
    return safeFilename(decodeURIComponent(candidate), fallback);
  } catch {
    return safeFilename(candidate, fallback);
  }
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function downloadBase64Pdf(encoded: string, filename: string, invalidMessage: string): void {
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const binary = window.atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
    throw new Error(invalidMessage);
  }
  downloadBlob(new Blob([bytes], {type: "application/pdf"}), filename);
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => ({})) as {
    detail?: string | {message?: string; code?: string}; message?: string; error?: string;
  };
  const detail = typeof payload.detail === "string"
    ? payload.detail
    : payload.detail?.message || payload.detail?.code;
  return new Error(detail || payload.message || payload.error || `${fallback} (${response.status}).`);
}

function compactDigest(value: unknown): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= 22) return normalized;
  return `${normalized.slice(0, 12)}…${normalized.slice(-8)}`;
}

export default function FinalReviewWorkspace() {
  const [locale, setLocale] = useState<Locale>("en");
  const [service, setService] = useState<Service>("comprehensive");
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedService = query.get("service");
    if (requestedService === "express" || requestedService === "comprehensive") setService(requestedService);
    const requestedLocale: Locale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setLocale(requestedLocale);
    document.documentElement.lang = requestedLocale;
    setRunId(query.get("run_id") || "");
    setCustomerId(query.get("customer_id") || "default_customer");
    setProjectId(query.get("project_id") || "default_project");
  }, []);

  const copy = COPY[locale];
  const canonical = service === "comprehensive";
  const approvalId = useMemo(() => approvalIdFrom(result), [result]);
  const edition = useMemo(() => acceptedEditionFrom(result), [result]);
  const certificate = useMemo(() => reviewCertificateFrom(result), [result]);
  const report = useMemo(() => reportFrom(result), [result]);
  const approvedPackage = useMemo(() => approvedPackageFrom(result), [result]);
  const deliveryCertificate = asRecord(approvedPackage.certificate);
  const rawStatus = String(
    certificate.decision
      || result?.review_status
      || result?.acceptance_status
      || asRecord(result?.approval).status
      || result?.status
      || "",
  ).trim().toLowerCase();
  const delivery = approvedDeliveryFrom(result);
  const deliveryAllowed = result?.client_delivery_allowed === true
    || asRecord(result?.acceptance).client_delivery_allowed === true
    || delivery.client_delivery_allowed === true
    || approvedPackage.client_delivery_allowed === true;
  const ready = canonical
    ? Boolean(runId.trim() && adminToken.trim() && reviewer.trim() && reviewerRole.trim())
    : Boolean(LEGACY_API_URL && runId.trim() && adminToken.trim() && reviewer.trim());
  const identityReady = Boolean(runId.trim());
  const reportDigest = String(
    edition.report_artifact_digest
      || asRecord(result?.review_context).artifact_digest
      || "",
  );
  const certificateDigest = String(certificate.approval_certificate_sha256 || "");
  const manifestDigest = String(edition.accepted_edition_manifest_sha256 || "");
  const packageDigest = String(approvedPackage.zip_sha256 || "");
  const deliveryCertificateDigest = String(
    deliveryCertificate.delivery_authorization_certificate_sha256 || "",
  );

  function legacyHeaders(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken.trim(),
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  function canonicalHeaders(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken.trim(),
      Accept: "application/json",
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  function scopeQuery(): URLSearchParams {
    return new URLSearchParams({
      customer_id: customerId.trim() || "default_customer",
      project_id: projectId.trim() || "default_project",
    });
  }

  function legacyStatusUrl(): string {
    return `${LEGACY_API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}?${scopeQuery()}`;
  }

  function canonicalUrl(path: string): string {
    return new URL(`/api/nico${path}`, window.location.origin).href;
  }

  function canonicalStatusUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}`);
  }

  function canonicalReviewUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review`);
  }

  function canonicalDeliveryUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/approved-delivery-package`);
  }

  async function requestJson(url: string, options: RequestInit = {}): Promise<ReviewResponse> {
    const response = await fetch(url, {cache: "no-store", ...options});
    if (!response.ok) throw await responseError(response, copy.loadFailed);
    try {
      return await response.json() as ReviewResponse;
    } catch {
      throw new Error(copy.loadFailed);
    }
  }

  async function loadStatus(event?: FormEvent): Promise<ReviewResponse | null> {
    event?.preventDefault();
    if (!ready) {
      setError(canonical ? copy.enterReviewer : copy.enterLegacy);
      return null;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const payload = canonical
        ? await requestJson(canonicalStatusUrl(), {headers: canonicalHeaders()})
        : await requestJson(legacyStatusUrl(), {headers: legacyHeaders()});
      setResult(payload);
      setNotice(copy.loaded);
      return payload;
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : copy.loadFailed);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function ensureLegacyReview(current: ReviewResponse): Promise<ReviewResponse> {
    if (approvalIdFrom(current)) return current;
    return requestJson(
      `${LEGACY_API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/request`,
      {
        method: "POST",
        headers: legacyHeaders(true),
        body: JSON.stringify({
          customer_id: customerId.trim() || "default_customer",
          project_id: projectId.trim() || "default_project",
          requester: reviewer.trim(),
          evidence: [copy.defaultApprovalReason],
        }),
      },
    );
  }

  async function approvedLegacyStatus(mutation: ReviewResponse): Promise<ReviewResponse> {
    try {
      const latest = await requestJson(legacyStatusUrl(), {headers: legacyHeaders()});
      return mergeReviewResponses(latest, mutation);
    } catch {
      return mutation;
    }
  }

  async function downloadCanonicalPdf(source: ReviewResponse): Promise<void> {
    const exactReport = reportFrom(source);
    const encoded = String(exactReport.pdf_base64 || "");
    if (!encoded) throw new Error(copy.pdfMissing);
    const fallback = `nico-comprehensive-${runId.trim()}-accepted-edition.pdf`;
    downloadBase64Pdf(
      encoded,
      safeFilename(String(exactReport.pdf_filename || ""), fallback),
      copy.invalidPdf,
    );
  }

  async function downloadCanonicalPackage(): Promise<void> {
    const response = await fetch(canonicalDeliveryUrl(), {
      cache: "no-store",
      headers: {
        ...canonicalHeaders(),
        Accept: "application/zip",
      },
    });
    if (!response.ok) throw await responseError(response, copy.packageMissing);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 2 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
      throw new Error(copy.invalidPackage);
    }
    const fallback = `nico-strategic-delivery-${runId.trim()}-APPROVED.zip`;
    downloadBlob(
      new Blob([bytes], {type: "application/zip"}),
      filenameFromResponse(response, fallback),
    );
  }

  async function downloadLegacyPdf(source: ReviewResponse): Promise<void> {
    const approved = approvedDeliveryFrom(source);
    const fallback = `nico-${service}-${runId.trim()}-approved-final-report.pdf`;
    const embedded = String(approved.pdf_base64 || approved.approved_pdf_base64 || "");
    if (embedded) {
      downloadBase64Pdf(
        embedded,
        safeFilename(String(approved.pdf_filename || ""), fallback),
        copy.invalidPdf,
      );
      return;
    }
    const response = await fetch(
      `${LEGACY_API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/approved-pdf?${scopeQuery()}`,
      {cache: "no-store", headers: legacyHeaders()},
    );
    if (!response.ok) throw await responseError(response, copy.pdfMissing);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
      throw new Error(copy.invalidPdf);
    }
    downloadBlob(new Blob([bytes], {type: "application/pdf"}), filenameFromResponse(response, fallback));
  }

  async function submitCanonicalDecision(decision: "approved" | Decision): Promise<ReviewResponse> {
    const reason = decision === "approved"
      ? note.trim() || copy.defaultApprovalReason
      : note.trim();
    return requestJson(
      canonicalReviewUrl(),
      {
        method: "POST",
        headers: canonicalHeaders(true),
        body: JSON.stringify({
          review_authorized: true,
          authorization_confirmed: true,
          reviewer: reviewer.trim(),
          reviewer_role: reviewerRole.trim(),
          decision,
          decision_reason: reason,
        }),
      },
    );
  }

  async function approveAndDownload(): Promise<void> {
    if (!ready || !confirmed) {
      setError(copy.confirmFirst);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (canonical) {
        const reviewed = await submitCanonicalDecision("approved");
        setResult(reviewed);
        await downloadCanonicalPdf(reviewed);
      } else {
        let current = result || await requestJson(legacyStatusUrl(), {headers: legacyHeaders()});
        current = await ensureLegacyReview(current);
        const exactApprovalId = approvalIdFrom(current);
        if (!exactApprovalId) throw new Error(copy.approvalFailed);
        const approved = await requestJson(
          `${LEGACY_API_URL}/operations/final-review/${service}/${encodeURIComponent(exactApprovalId)}/approved`,
          {
            method: "POST",
            headers: legacyHeaders(true),
            body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
          },
        );
        const latest = await approvedLegacyStatus(approved);
        setResult(latest);
        await downloadLegacyPdf(latest);
      }
      setNotice(copy.approvedNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.approvalFailed);
    } finally {
      setLoading(false);
    }
  }

  async function recordOtherDecision(state: Decision): Promise<void> {
    if (!ready || !note.trim()) {
      setError(copy.decisionNoteRequired);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (canonical) {
        setResult(await submitCanonicalDecision(state));
      } else {
        let current = result || await requestJson(legacyStatusUrl(), {headers: legacyHeaders()});
        current = await ensureLegacyReview(current);
        const exactApprovalId = approvalIdFrom(current);
        if (!exactApprovalId) throw new Error(copy.decisionFailed);
        const legacyState = state === "request_more_evidence" ? "needs_more_evidence" : "rejected";
        const mutation = await requestJson(
          `${LEGACY_API_URL}/operations/final-review/${service}/${encodeURIComponent(exactApprovalId)}/${legacyState}`,
          {
            method: "POST",
            headers: legacyHeaders(true),
            body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
          },
        );
        setResult(await approvedLegacyStatus(mutation));
      }
      setNotice(state === "request_more_evidence" ? copy.evidenceNotice : copy.rejectedNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.decisionFailed);
    } finally {
      setLoading(false);
    }
  }

  async function downloadApprovedAgain(): Promise<void> {
    try {
      setError("");
      if (!result) throw new Error(copy.pdfMissing);
      if (canonical) await downloadCanonicalPdf(result);
      else await downloadLegacyPdf(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.pdfMissing);
    }
  }

  async function downloadApprovedPackage(): Promise<void> {
    try {
      setError("");
      if (!canonical || !deliveryAllowed) throw new Error(copy.packageMissing);
      await downloadCanonicalPackage();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.packageMissing);
    }
  }

  return <main className={styles.shell} data-review-contract={canonical ? "accepted-edition-v2" : "legacy-operator-review"}>
    <section className={styles.hero}>
      <div className={styles.heroGlow} aria-hidden="true" />
      <p className={styles.eyebrow}>{copy.eyebrow}</p>
      <h1>{copy.title}</h1>
      <p className={styles.lead}>{copy.lead}</p>
      <div className={styles.identityStrip}>
        <div><span>{copy.assessment}</span><strong>{service === "comprehensive" ? "Strategic" : "Express"}</strong></div>
        <div><span>{copy.exactRun}</span><strong>{runId.trim() || copy.directRun}</strong></div>
        <div className={identityReady ? styles.identityReady : styles.identityMissing}><span>{copy.identity}</span><strong>{identityReady ? copy.bound : copy.missing}</strong></div>
      </div>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>1</span><div><p className={styles.kicker}>{copy.secureAccess}</p><h2>{copy.identifyReviewer}</h2><p>{copy.identityAttached}</p></div></div>
      <form className={styles.form} onSubmit={loadStatus}>
        <label className={styles.reviewerField}>{copy.reviewer}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder={copy.reviewerPlaceholder} autoComplete="name" /></label>
        {canonical ? <label className={styles.tokenField}>{copy.reviewerRole}<input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} placeholder={copy.reviewerRolePlaceholder} autoComplete="organization-title" /></label> : null}
        <label className={styles.tokenField}>{copy.operatorToken}<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} placeholder={copy.secureToken} autoComplete="off" spellCheck={false} /></label>
        <button className={styles.primary} type="submit" disabled={loading || !ready}>{loading ? copy.opening : result ? copy.refresh : copy.open}</button>
        <details className={styles.advanced}><summary>{copy.advanced}</summary><div className={styles.advancedGrid}>
          <label>{copy.assessmentType}<select value={service} onChange={(event) => {setService(event.target.value as Service); setResult(null); setConfirmed(false);}}><option value="comprehensive">Strategic</option><option value="express">Express</option></select></label>
          <label>{copy.exactRunId}<input value={runId} onChange={(event) => {setRunId(event.target.value); setResult(null); setConfirmed(false);}} placeholder="comprun_… or express_run_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
          {!canonical ? <><label>{copy.customerId}<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>{copy.projectId}<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label></> : null}
        </div></details>
      </form>
      <p className={styles.securityNote}>{canonical ? copy.canonicalSecurity : copy.legacySecurity}</p>
      <div className={styles.feedback} aria-live="polite">{error ? <div className={styles.error} role="alert">{error}</div> : null}{!error && notice ? <div className={styles.success}>{notice}</div> : null}</div>
    </section>

    <section className={`${styles.panel} ${result ? styles.approvalActive : styles.approvalWaiting}`}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>2</span><div><p className={styles.kicker}>{copy.finalDecision}</p><h2>{copy.approveHeading}</h2><p>{copy.approveLead}</p></div></div>
      <div className={styles.statusGrid}>
        <article className={styles.statusCard}><span>{copy.review}</span><strong>{rawStatus ? rawStatus.replaceAll("_", " ") : copy.waiting}</strong></article>
        <article className={deliveryAllowed ? styles.statusCardReady : styles.statusCardBlocked}><span>{copy.delivery}</span><strong>{deliveryAllowed ? copy.authorized : copy.blocked}</strong></article>
      </div>
      {canonical && result ? <div className={styles.statusGrid}>
        <article className={styles.statusCard}><span>{copy.reportDigest}</span><strong title={reportDigest}>{reportDigest ? compactDigest(reportDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.certificateDigest}</span><strong title={certificateDigest}>{certificateDigest ? compactDigest(certificateDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.manifestDigest}</span><strong title={manifestDigest}>{manifestDigest ? compactDigest(manifestDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.packageDigest}</span><strong title={packageDigest}>{packageDigest ? compactDigest(packageDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.deliveryCertificateDigest}</span><strong title={deliveryCertificateDigest}>{deliveryCertificateDigest ? compactDigest(deliveryCertificateDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>PDF</span><strong>{report.pdf_filename ? String(report.pdf_filename) : copy.notIssued}</strong></article>
      </div> : null}
      {!result ? <div className={styles.emptyState}><strong>{copy.emptyTitle}</strong><span>{copy.emptyBody}</span></div> : <>
        <label className={styles.confirmRow}><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span><strong>{copy.reviewedExact}</strong><small>{copy.reviewedDetail}</small></span></label>
        <details className={styles.noteDetails}><summary>{copy.approvalNote}</summary><label>{copy.approvalNoteLabel}<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={copy.approvalPlaceholder} /></label></details>
        <div className={styles.downloadActions}><button className={styles.approve} type="button" disabled={!confirmed || loading || deliveryAllowed} onClick={approveAndDownload}>{loading ? copy.recording : deliveryAllowed ? copy.alreadyApproved : copy.approveDownload}</button>{deliveryAllowed ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadApprovedAgain}>{copy.downloadAgain}</button> : null}{canonical && deliveryAllowed ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadApprovedPackage}>{copy.downloadPackage}</button> : null}</div>
        <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>{deliveryAllowed ? copy.readyDelivery : copy.blockedDelivery}</div>
        <details className={styles.otherDecisions}><summary>{copy.otherDecision}</summary><p>{copy.otherDecisionLead}</p><div className={styles.decisionActions}><button type="button" disabled={loading || deliveryAllowed} onClick={() => recordOtherDecision("request_more_evidence")}>{copy.requestEvidence}</button><button className={styles.reject} type="button" disabled={loading || deliveryAllowed} onClick={() => recordOtherDecision("rejected")}>{copy.reject}</button></div></details>
      </>}
    </section>

    {result ? <section className={`${styles.panel} ${styles.recordPanel}`}><details className={styles.record}><summary>{copy.technicalRecord}</summary><pre className={styles.code}>{JSON.stringify(result, null, 2)}</pre></details></section> : null}
  </main>;
}

/* Legacy Express compatibility remains deliberately isolated: Operator admin token; type="password"; await ensureLegacyReview(current); /approved`; Request more evidence; Reject delivery. */
