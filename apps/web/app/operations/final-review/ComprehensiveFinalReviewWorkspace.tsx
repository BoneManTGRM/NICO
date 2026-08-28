"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import styles from "./final-review.module.css";

type Decision = "request_more_evidence" | "rejected";
type Locale = "en" | "es-MX";
type JsonRecord = Record<string, unknown>;

const AUTHORIZED_REVIEWER_ROLES = [
  {value: "Cybersecurity specialist", en: "Cybersecurity specialist", es: "Especialista en ciberseguridad"},
  {value: "Cybersecurity reviewer", en: "Cybersecurity reviewer", es: "Revisor de ciberseguridad"},
  {value: "Security specialist", en: "Security specialist", es: "Especialista en seguridad"},
  {value: "Security reviewer", en: "Security reviewer", es: "Revisor de seguridad"},
] as const;

type ReviewResponse = {
  status?: string;
  review_status?: string;
  acceptance_status?: string;
  human_review_completed?: boolean;
  approval_id?: string;
  client_delivery_allowed?: boolean;
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
  review_artifact_identity?: JsonRecord;
};

const COPY = {
  en: {
    eyebrow: "NICO COMPREHENSIVE · INTERNAL QUALITY GATE",
    title: "Internal final review and client-ready authorization.",
    lead: "Review the exact immutable NICO Comprehensive report, confirm its evidence boundary, and authorize only the artifact set your team actually examined.",
    assessment: "Assessment",
    comprehensive: "Comprehensive",
    exactRun: "Exact run",
    identity: "Identity",
    bound: "Bound",
    missing: "Missing",
    directRun: "Open this page from a completed Comprehensive assessment",
    secureAccess: "SECURE ACCESS",
    identifyReviewer: "Identify the authorized reviewer",
    identityAttached: "The exact run is attached automatically when this page is opened from a completed assessment. You can also paste an exact Comprehensive run ID below.",
    reviewer: "Authorized reviewer",
    reviewerPlaceholder: "Full name or accountable identity",
    reviewerRole: "Reviewer role",
    reviewerRolePlaceholder: "Select an authorized reviewer role",
    operatorToken: "Operator admin token",
    secureToken: "Secure token",
    opening: "Opening review…",
    refresh: "Refresh review",
    open: "Open review",
    exactIdentity: "Confirm exact report identity",
    exactRunId: "Exact Comprehensive run ID",
    security: "The reviewer identity and role are persisted in the approval certificate. The operator token stays only in this open page. No secret is stored in the URL or browser storage.",
    enterReviewer: "Enter the exact Comprehensive run ID, operator token, authorized reviewer, and reviewer role.",
    loaded: "The immutable Comprehensive review package is loaded. Confirm it below when ready.",
    loadFailed: "Unable to load final review.",
    finalDecision: "FINAL DECISION",
    approveHeading: "Approve the exact accepted edition",
    approveLead: "Download and review the immutable PDF first. A separate controlled action then binds your approval to those exact bytes.",
    review: "Review",
    delivery: "Client-ready",
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
    downloadReview: "Download exact PDF to review",
    downloadAgain: "Download approved PDF again",
    downloadPackage: "Download approved delivery package",
    readyDelivery: "This exact immutable edition and its certified delivery package are approved and client-ready.",
    blockedDelivery: "Client-ready release remains blocked until a valid internal approval certificate matches the current artifact set.",
    pendingAuthorization: "Human approval is recorded for this exact edition. Client delivery remains blocked until its delivery authorization package and certificate are valid.",
    authorizationConfirm: "I explicitly authorize client delivery of this exact approved edition and its certified package.",
    authorizeDelivery: "Authorize client delivery",
    authorizingDelivery: "Recording delivery authorization…",
    authorizationNotice: "Client delivery authorization recorded for the exact accepted edition.",
    authorizationFailed: "Unable to authorize client delivery.",
    confirmAuthorizationFirst: "Confirm the separate client-delivery authorization action.",
    defaultAuthorizationReason: "Authorized reviewer explicitly authorized client delivery of the exact accepted edition and its immutable certified package.",
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
    approvedNotice: "Human approval recorded and the accepted report downloaded. Client delivery remains blocked pending the separate authorization action.",
    reviewDownloadNotice: "The exact pre-approval PDF was downloaded for review. Approval remains pending.",
    evidenceNotice: "More evidence requested. Delivery remains blocked. Start a new assessment with the requested evidence; this unchanged report cannot later be approved.",
    rejectedNotice: "Report rejected. Delivery remains blocked.",
    approvalFailed: "Unable to approve and download the final report.",
    decisionFailed: "Unable to record the review decision.",
    pdfMissing: "The reviewed response did not contain the exact PDF artifact.",
    invalidPdf: "The approved PDF failed browser integrity validation.",
    packageMissing: "The approved delivery package is unavailable for this exact run.",
    invalidPackage: "The approved delivery package failed ZIP integrity validation.",
    defaultApprovalReason: "Authorized reviewer confirmed the exact immutable report, scorecard, disclosed evidence limitations, artifact identity, and delivery boundary.",
    reviewerQueue: "Open the exception-first technical review queue for this exact run",
  },
  "es-MX": {
    eyebrow: "NICO COMPREHENSIVE · CONTROL INTERNO DE CALIDAD",
    title: "Revisión final interna y autorización para el cliente.",
    lead: "Revisa el informe NICO Comprehensive inmutable exacto, confirma su límite de evidencia y autoriza únicamente el conjunto de artefactos que examinó tu equipo.",
    assessment: "Evaluación",
    comprehensive: "Comprehensive",
    exactRun: "Ejecución exacta",
    identity: "Identidad",
    bound: "Vinculada",
    missing: "Faltante",
    directRun: "Abre esta página desde una evaluación Comprehensive terminada",
    secureAccess: "ACCESO SEGURO",
    identifyReviewer: "Identifica al revisor autorizado",
    identityAttached: "La ejecución exacta se vincula automáticamente cuando esta página se abre desde una evaluación terminada. También puedes pegar abajo un ID exacto de Comprehensive.",
    reviewer: "Revisor autorizado",
    reviewerPlaceholder: "Nombre completo o identidad responsable",
    reviewerRole: "Función del revisor",
    reviewerRolePlaceholder: "Selecciona una función de revisor autorizada",
    operatorToken: "Token de administrador del operador",
    secureToken: "Token seguro",
    opening: "Abriendo revisión…",
    refresh: "Actualizar revisión",
    open: "Abrir revisión",
    exactIdentity: "Confirmar identidad exacta del informe",
    exactRunId: "ID exacto de ejecución Comprehensive",
    security: "La identidad y función del revisor se conservan en el certificado de aprobación. El token del operador permanece únicamente en esta página abierta. Ningún secreto se guarda en la URL ni en el almacenamiento del navegador.",
    enterReviewer: "Ingresa el ID exacto de Comprehensive, el token del operador, el revisor autorizado y su función.",
    loaded: "El paquete inmutable de revisión Comprehensive está cargado. Confírmalo abajo cuando estés listo.",
    loadFailed: "No fue posible cargar la revisión final.",
    finalDecision: "DECISIÓN FINAL",
    approveHeading: "Aprueba la edición aceptada exacta",
    approveLead: "Primero descarga y revisa el PDF inmutable. Una acción controlada separada vincula después tu aprobación a esos bytes exactos.",
    review: "Revisión",
    delivery: "Lista para el cliente",
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
    downloadReview: "Descargar PDF exacto para revisión",
    downloadAgain: "Descargar nuevamente el PDF aprobado",
    downloadPackage: "Descargar paquete de entrega aprobado",
    readyDelivery: "Esta edición inmutable exacta y su paquete de entrega certificado están aprobados para entrega controlada al cliente.",
    blockedDelivery: "La entrega permanece bloqueada hasta que un certificado válido coincida con el conjunto actual de artefactos.",
    pendingAuthorization: "La aprobación humana está registrada para esta edición exacta. La entrega al cliente permanece bloqueada hasta que sean válidos el paquete y el certificado de autorización de entrega.",
    authorizationConfirm: "Autorizo explícitamente la entrega al cliente de esta edición exacta aprobada y su paquete certificado.",
    authorizeDelivery: "Autorizar entrega al cliente",
    authorizingDelivery: "Registrando autorización de entrega…",
    authorizationNotice: "Se registró la autorización de entrega al cliente para la edición aceptada exacta.",
    authorizationFailed: "No fue posible autorizar la entrega al cliente.",
    confirmAuthorizationFirst: "Confirma la acción separada de autorización de entrega al cliente.",
    defaultAuthorizationReason: "El revisor autorizado autorizó explícitamente la entrega al cliente de la edición aceptada exacta y su paquete certificado inmutable.",
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
    approvedNotice: "Se registró la aprobación humana y se descargó el informe aceptado. La entrega al cliente permanece bloqueada hasta la acción de autorización separada.",
    reviewDownloadNotice: "Se descargó el PDF exacto previo a la aprobación para revisión. La aprobación sigue pendiente.",
    evidenceNotice: "Se solicitó más evidencia. La entrega permanece bloqueada. Inicia una nueva evaluación con la evidencia solicitada; este informe sin cambios no podrá aprobarse después.",
    rejectedNotice: "Informe rechazado. La entrega permanece bloqueada.",
    approvalFailed: "No fue posible aprobar y descargar el informe final.",
    decisionFailed: "No fue posible registrar la decisión de revisión.",
    pdfMissing: "La respuesta revisada no contiene el artefacto PDF exacto.",
    invalidPdf: "El PDF aprobado no superó la validación de integridad del navegador.",
    packageMissing: "El paquete de entrega aprobado no está disponible para esta ejecución exacta.",
    invalidPackage: "El paquete de entrega aprobado no superó la validación de integridad ZIP.",
    defaultApprovalReason: "El revisor autorizado confirmó el informe inmutable exacto, la puntuación, las limitaciones de evidencia declaradas, la identidad del artefacto y el límite de entrega.",
    reviewerQueue: "Abrir la cola técnica por excepción para esta ejecución exacta",
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

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const digest = await window.crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function downloadBase64Pdf(
  encoded: string,
  filename: string,
  invalidMessage: string,
  expectedSha256: string,
): Promise<string> {
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const binary = window.atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
    throw new Error(invalidMessage);
  }
  const actualSha256 = await sha256Hex(bytes);
  if (!/^[0-9a-f]{64}$/i.test(expectedSha256) || actualSha256 !== expectedSha256.toLowerCase()) {
    throw new Error(invalidMessage);
  }
  downloadBlob(new Blob([bytes], {type: "application/pdf"}), filename);
  return actualSha256;
}

async function responseError(response: Response, fallback: string, locale: Locale): Promise<Error> {
  const payload = await response.json().catch(() => ({})) as {
    detail?: string | {message?: string; code?: string; reason?: string};
    message?: string;
    error?: string;
  };
  const detail = typeof payload.detail === "string"
    ? payload.detail
    : payload.detail?.message || payload.detail?.code || payload.detail?.reason;
  if (locale === "es-MX") return new Error(`${fallback} (${response.status}).`);
  return new Error(detail || payload.message || payload.error || `${fallback} (${response.status}).`);
}

function compactDigest(value: unknown): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= 22) return normalized;
  return `${normalized.slice(0, 12)}…${normalized.slice(-8)}`;
}

function reviewStatusLabel(value: string, locale: Locale): string {
  const normalized = value.trim().toLowerCase();
  const labels: Record<string, [string, string]> = {
    approved: ["Approved", "Aprobada"],
    rejected: ["Rejected", "Rechazada"],
    request_more_evidence: ["More evidence requested", "Se solicitó más evidencia"],
    review_required: ["Human review required", "Se requiere revisión humana"],
    pending: ["Pending", "Pendiente"],
    blocked: ["Blocked", "Bloqueada"],
  };
  const matched = labels[normalized];
  if (matched) return locale === "es-MX" ? matched[1] : matched[0];
  return normalized
    ? normalized.replaceAll("_", " ")
    : locale === "es-MX" ? "Esperando acceso seguro" : "Waiting for secure access";
}

export default function ComprehensiveFinalReviewWorkspace() {
  const [locale, setLocale] = useState<Locale>("en");
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [downloadedArtifactDigest, setDownloadedArtifactDigest] = useState("");
  const [deliveryConfirmed, setDeliveryConfirmed] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale: Locale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setLocale(requestedLocale);
    document.documentElement.lang = requestedLocale;
    setRunId(query.get("run_id") || "");
  }, []);

  const copy = COPY[locale];
  const ready = Boolean(runId.trim() && adminToken.trim() && reviewer.trim() && reviewerRole.trim());
  const identityReady = Boolean(runId.trim());
  const edition = useMemo(() => acceptedEditionFrom(result), [result]);
  const certificate = useMemo(() => reviewCertificateFrom(result), [result]);
  const report = useMemo(() => reportFrom(result), [result]);
  const reviewArtifactIdentity = asRecord(result?.review_artifact_identity);
  const currentReviewDigest = String(
    reviewArtifactIdentity.report_artifact_digest || "",
  );
  const currentReviewPdfDigest = String(
    asRecord(asRecord(reviewArtifactIdentity.artifact_digests).pdf).sha256 || "",
  ).toLowerCase();
  const approvedPackage = useMemo(() => approvedPackageFrom(result), [result]);
  const deliveryCertificate = asRecord(approvedPackage.certificate);
  const delivery = approvedDeliveryFrom(result);
  const deliveryAllowed = result?.client_delivery_allowed === true
    || asRecord(result?.acceptance).client_delivery_allowed === true
    || delivery.client_delivery_allowed === true
    || approvedPackage.client_delivery_allowed === true;
  const rawStatus = String(
    certificate.decision
      || result?.review_status
      || asRecord(result?.approval).status
      || result?.status
      || "",
  ).trim().toLowerCase();
  const runStatus = String(result?.status || "").trim().toLowerCase();
  const approvalCompleted = rawStatus === "approved" || runStatus === "approved";
  const reportDigest = String(
    edition.report_artifact_digest
      || currentReviewDigest
      || asRecord(result?.review_context).artifact_digest
      || "",
  );
  const certificateDigest = String(certificate.approval_certificate_sha256 || "");
  const manifestDigest = String(edition.accepted_edition_manifest_sha256 || "");
  const packageDigest = String(approvedPackage.zip_sha256 || "");
  const deliveryCertificateDigest = String(
    deliveryCertificate.delivery_authorization_certificate_sha256 || "",
  );

  function canonicalUrl(path: string): string {
    return new URL(`/api/nico${path}`, window.location.origin).href;
  }

  function statusUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}`);
  }

  function reviewUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review`);
  }

  function deliveryUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/approved-delivery-package`);
  }

  function deliveryAuthorizationUrl(): string {
    return canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/authorize-delivery`);
  }

  function headers(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken.trim(),
      Accept: "application/json",
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  async function requestJson(url: string, options: RequestInit = {}): Promise<ReviewResponse> {
    const response = await fetch(url, {cache: "no-store", ...options});
    if (!response.ok) throw await responseError(response, copy.loadFailed, locale);
    try {
      return await response.json() as ReviewResponse;
    } catch {
      throw new Error(copy.loadFailed);
    }
  }

  async function loadStatus(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    if (!ready) {
      setError(copy.enterReviewer);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    setDownloadedArtifactDigest("");
    setDeliveryConfirmed(false);
    setConfirmed(false);
    try {
      setResult(await requestJson(statusUrl(), {headers: headers()}));
      setNotice(copy.loaded);
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : copy.loadFailed);
    } finally {
      setLoading(false);
    }
  }

  async function submitDecision(decision: "approved" | Decision): Promise<ReviewResponse> {
    const reason = decision === "approved"
      ? note.trim() || copy.defaultApprovalReason
      : note.trim();
    return requestJson(reviewUrl(), {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify({
        review_authorized: true,
        authorization_confirmed: true,
        reviewer: reviewer.trim(),
        reviewer_role: reviewerRole.trim(),
        decision,
        decision_reason: reason,
        expected_artifact_identity: reviewArtifactIdentity,
      }),
    });
  }

  async function downloadApprovedPdf(source: ReviewResponse): Promise<string> {
    const exactReport = reportFrom(source);
    const encoded = String(exactReport.pdf_base64 || "");
    if (!encoded) throw new Error(copy.pdfMissing);
    const sourceEdition = acceptedEditionFrom(source);
    const sourceIdentity = asRecord(source.review_artifact_identity);
    const expectedPdfSha256 = String(
      asRecord(asRecord(sourceIdentity.artifact_digests).pdf).sha256
        || asRecord(asRecord(sourceEdition.artifact_digests).pdf).sha256
        || "",
    ).toLowerCase();
    const fallback = `nico-comprehensive-${runId.trim()}-accepted-edition.pdf`;
    return downloadBase64Pdf(
      encoded,
      safeFilename(String(exactReport.pdf_filename || ""), fallback),
      copy.invalidPdf,
      expectedPdfSha256,
    );
  }

  async function downloadReviewPdf(): Promise<void> {
    try {
      setError("");
      if (!result) throw new Error(copy.pdfMissing);
      if (!currentReviewPdfDigest) throw new Error(copy.pdfMissing);
      const verifiedPdfDigest = await downloadApprovedPdf(result);
      setDownloadedArtifactDigest(verifiedPdfDigest);
      setNotice(copy.reviewDownloadNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.pdfMissing);
    }
  }

  async function downloadApprovedPackage(): Promise<void> {
    const response = await fetch(deliveryUrl(), {
      cache: "no-store",
      headers: {...headers(), Accept: "application/zip"},
    });
    if (!response.ok) throw await responseError(response, copy.packageMissing, locale);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 2 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
      throw new Error(copy.invalidPackage);
    }
    downloadBlob(
      new Blob([bytes], {type: "application/zip"}),
      filenameFromResponse(response, `nico-comprehensive-delivery-${runId.trim()}-APPROVED.zip`),
    );
  }

  async function approveAndDownload(): Promise<void> {
    if (approvalCompleted) {
      setError(copy.alreadyApproved);
      return;
    }
    if (
      !ready
      || !confirmed
      || !currentReviewPdfDigest
      || downloadedArtifactDigest !== currentReviewPdfDigest
    ) {
      setError(copy.confirmFirst);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const reviewed = await submitDecision("approved");
      setResult(reviewed);
      setDeliveryConfirmed(false);
      await downloadApprovedPdf(reviewed);
      setNotice(copy.approvedNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.approvalFailed);
    } finally {
      setLoading(false);
    }
  }

  async function recordOtherDecision(decision: Decision): Promise<void> {
    if (!ready || !note.trim()) {
      setError(copy.decisionNoteRequired);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      setResult(await submitDecision(decision));
      setNotice(decision === "request_more_evidence" ? copy.evidenceNotice : copy.rejectedNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.decisionFailed);
    } finally {
      setLoading(false);
    }
  }

  async function authorizeClientDelivery(): Promise<void> {
    if (!ready || !approvalCompleted || deliveryAllowed || !deliveryConfirmed) {
      setError(copy.confirmAuthorizationFirst);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const authorized = await requestJson(deliveryAuthorizationUrl(), {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({
          delivery_authorized: true,
          authorization_confirmed: true,
          authorizer: reviewer.trim(),
          authorizer_role: reviewerRole.trim(),
          authorization_reason: note.trim() || copy.defaultAuthorizationReason,
          expected_artifact_identity: reviewArtifactIdentity,
        }),
      });
      setResult(authorized);
      setDeliveryConfirmed(false);
      setNotice(copy.authorizationNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.authorizationFailed);
    } finally {
      setLoading(false);
    }
  }

  async function downloadAgain(): Promise<void> {
    try {
      setError("");
      if (!result) throw new Error(copy.pdfMissing);
      await downloadApprovedPdf(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.pdfMissing);
    }
  }

  async function downloadPackage(): Promise<void> {
    try {
      setError("");
      if (!deliveryAllowed) throw new Error(copy.packageMissing);
      await downloadApprovedPackage();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.packageMissing);
    }
  }

  const reviewerQueueHref = `/operations/reviewer-queue?run_id=${encodeURIComponent(runId.trim())}&lang=${encodeURIComponent(locale)}`;

  return <main className={styles.shell} data-review-contract="accepted-edition-v2">
    <section className={styles.hero}>
      <div className={styles.heroGlow} aria-hidden="true" />
      <p className={styles.eyebrow}>{copy.eyebrow}</p>
      <h1>{copy.title}</h1>
      <p className={styles.lead}>{copy.lead}</p>
      <div className={styles.identityStrip}>
        <div><span>{copy.assessment}</span><strong>{copy.comprehensive}</strong></div>
        <div><span>{copy.exactRun}</span><strong>{runId.trim() || copy.directRun}</strong></div>
        <div className={identityReady ? styles.identityReady : styles.identityMissing}><span>{copy.identity}</span><strong>{identityReady ? copy.bound : copy.missing}</strong></div>
      </div>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>1</span><div><p className={styles.kicker}>{copy.secureAccess}</p><h2>{copy.identifyReviewer}</h2><p>{copy.identityAttached}</p></div></div>
      <form className={styles.form} onSubmit={loadStatus}>
        <label className={styles.reviewerField}>{copy.reviewer}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder={copy.reviewerPlaceholder} autoComplete="name" /></label>
        <label className={styles.tokenField}>{copy.reviewerRole}<select value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)}>
          <option value="">{copy.reviewerRolePlaceholder}</option>
          {AUTHORIZED_REVIEWER_ROLES.map((role) => <option value={role.value} key={role.value}>{locale === "es-MX" ? role.es : role.en}</option>)}
        </select></label>
        <label className={styles.tokenField}>{copy.operatorToken}<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} placeholder={copy.secureToken} autoComplete="off" spellCheck={false} /></label>
        <button className={styles.primary} type="submit" disabled={loading || !ready}>{loading ? copy.opening : result ? copy.refresh : copy.open}</button>
        <details className={styles.advanced}><summary>{copy.exactIdentity}</summary><div className={styles.advancedGrid}>
          <label>{copy.assessment}<input value={copy.comprehensive} readOnly aria-readonly="true" /></label>
          <label>{copy.exactRunId}<input value={runId} onChange={(event) => {setRunId(event.target.value); setResult(null); setConfirmed(false); setDeliveryConfirmed(false); setDownloadedArtifactDigest("");}} placeholder="comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        </div></details>
      </form>
      <p className={styles.securityNote}>{copy.security}</p>
      {runId.trim() ? <p className={styles.securityNote}><a href={reviewerQueueHref}>{copy.reviewerQueue}</a></p> : null}
      <div className={styles.feedback} aria-live="polite">{error ? <div className={styles.error} role="alert">{error}</div> : null}{!error && notice ? <div className={styles.success}>{notice}</div> : null}</div>
    </section>

    <section className={`${styles.panel} ${result ? styles.approvalActive : styles.approvalWaiting}`}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>2</span><div><p className={styles.kicker}>{copy.finalDecision}</p><h2>{copy.approveHeading}</h2><p>{copy.approveLead}</p></div></div>
      <div className={styles.statusGrid}>
        <article className={styles.statusCard}><span>{copy.review}</span><strong>{reviewStatusLabel(rawStatus, locale)}</strong></article>
        <article className={deliveryAllowed ? styles.statusCardReady : styles.statusCardBlocked}><span>{copy.delivery}</span><strong>{deliveryAllowed ? copy.authorized : copy.blocked}</strong></article>
      </div>
      {result ? <div className={styles.statusGrid}>
        <article className={styles.statusCard}><span>{copy.reportDigest}</span><strong title={reportDigest}>{reportDigest ? compactDigest(reportDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.certificateDigest}</span><strong title={certificateDigest}>{certificateDigest ? compactDigest(certificateDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.manifestDigest}</span><strong title={manifestDigest}>{manifestDigest ? compactDigest(manifestDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.packageDigest}</span><strong title={packageDigest}>{packageDigest ? compactDigest(packageDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>{copy.deliveryCertificateDigest}</span><strong title={deliveryCertificateDigest}>{deliveryCertificateDigest ? compactDigest(deliveryCertificateDigest) : copy.notIssued}</strong></article>
        <article className={styles.statusCard}><span>PDF</span><strong>{report.pdf_filename ? String(report.pdf_filename) : copy.notIssued}</strong></article>
      </div> : null}
      {!result ? <div className={styles.emptyState}><strong>{copy.emptyTitle}</strong><span>{copy.emptyBody}</span></div> : <>
        <label className={styles.confirmRow}><input type="checkbox" checked={confirmed} disabled={downloadedArtifactDigest !== currentReviewPdfDigest || !currentReviewPdfDigest} onChange={(event) => setConfirmed(event.target.checked)} /><span><strong>{copy.reviewedExact}</strong><small>{copy.reviewedDetail}</small></span></label>
        <details className={styles.noteDetails}><summary>{copy.approvalNote}</summary><label>{copy.approvalNoteLabel}<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={copy.approvalPlaceholder} /></label></details>
        <div className={styles.downloadActions}>{!approvalCompleted ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadReviewPdf}>{copy.downloadReview}</button> : null}<button className={styles.approve} type="button" disabled={!confirmed || loading || approvalCompleted} onClick={approveAndDownload}>{approvalCompleted ? copy.alreadyApproved : loading ? copy.recording : copy.approveDownload}</button>{approvalCompleted ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadAgain}>{copy.downloadAgain}</button> : null}{deliveryAllowed ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadPackage}>{copy.downloadPackage}</button> : null}</div>
        {approvalCompleted && !deliveryAllowed ? <label className={styles.confirmRow}><input type="checkbox" checked={deliveryConfirmed} onChange={(event) => setDeliveryConfirmed(event.target.checked)} /><span><strong>{copy.authorizationConfirm}</strong></span></label> : null}
        {approvalCompleted && !deliveryAllowed ? <div className={styles.downloadActions}><button className={styles.approve} type="button" disabled={loading || !deliveryConfirmed} onClick={authorizeClientDelivery}>{loading ? copy.authorizingDelivery : copy.authorizeDelivery}</button></div> : null}
        <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>{deliveryAllowed ? copy.readyDelivery : approvalCompleted ? copy.pendingAuthorization : copy.blockedDelivery}</div>
        <details className={styles.otherDecisions}><summary>{copy.otherDecision}</summary><p>{copy.otherDecisionLead}</p><div className={styles.decisionActions}><button type="button" disabled={loading || approvalCompleted} onClick={() => recordOtherDecision("request_more_evidence")}>{copy.requestEvidence}</button><button className={styles.reject} type="button" disabled={loading || approvalCompleted} onClick={() => recordOtherDecision("rejected")}>{copy.reject}</button></div></details>
      </>}
    </section>

    {result ? <section className={`${styles.panel} ${styles.recordPanel}`}><details className={styles.record}><summary>{copy.technicalRecord}</summary><pre className={styles.code}>{JSON.stringify(result, null, 2)}</pre></details></section> : null}
  </main>;
}
