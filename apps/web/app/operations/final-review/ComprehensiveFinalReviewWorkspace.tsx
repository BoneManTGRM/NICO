"use client";

import {FormEvent, useEffect, useMemo, useRef, useState} from "react";
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
  operator_approval_status?: string;
  operator_approved_edition?: JsonRecord;
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
    title: "Approve the exact final assessment report.",
    lead: "A completed assessment can always produce its exact final assessment report. Human review, approval, and client delivery remain separate controlled states.",
    assessment: "Assessment",
    comprehensive: "Comprehensive",
    exactRun: "Exact run",
    identity: "Identity",
    bound: "Bound",
    missing: "Missing",
    directRun: "Open this page from a completed Comprehensive assessment",
    secureAccess: "SECURE ACCESS",
    identifyReviewer: "Open the exact completed assessment",
    identityAttached: "The exact run is attached automatically when this page is opened from a completed assessment. Reviewer name and role are optional metadata; the authenticated operator credential is the approval authority.",
    reviewer: "Reviewer name (optional)",
    reviewerPlaceholder: "Optional — blank uses authenticated operator metadata",
    reviewerRole: "Reviewer role (optional)",
    reviewerRolePlaceholder: "Optional — type test when testing",
    operatorToken: "Operator password",
    secureToken: "Enter your NICO operator password",
    opening: "Opening review…",
    refresh: "Refresh review",
    open: "Open review",
    exactIdentity: "Confirm exact report identity",
    exactRunId: "Exact Comprehensive run ID",
    security: "Use the private operator password configured for NICO in Railway. It stays only in this open page and is never stored in the URL or browser storage.",
    enterReviewer: "Enter the exact Comprehensive run ID and operator password. Reviewer name and role may be blank for approval; client delivery remains a separate, stricter action.",
    loaded: "The immutable Comprehensive review package is loaded. The final assessment report is available independently of optional reviewer/client metadata.",
    loadFailed: "Unable to load final review.",
    finalDecision: "FINAL REPORT AND REVIEW STATE",
    approveHeading: "Review and approve the exact assessment report",
    approveLead: "Download and review the report, confirm that exact PDF, then approve and download the final PDF. Reviewer name and role are optional metadata. A download or checked box alone does not record approval. Client delivery is a separate authorization.",
    review: "Report approval",
    specialistReview: "Specialist review",
    specialistIncomplete: "Not completed",
    specialistComplete: "Completed",
    operatorDisclosure: "Operator approval accepts this exact report with its disclosed limitations and outstanding specialist review, independent QC, and escalations. It does not mark that work complete or authorize client delivery.",
    delivery: "Client-ready",
    authorized: "Authorized",
    blocked: "Blocked",
    waiting: "Waiting for secure access",
    emptyTitle: "Nothing else to complete yet.",
    emptyBody: "Enter the exact run and operator password above, then open the exact completed assessment.",
    reviewedExact: "I reviewed this exact downloaded report and approve it with its disclosed limitations and outstanding review/QC.",
    reviewedDetail: "This records operator approval of this edition. Specialist review, independent QC, and client delivery remain separate.",
    approvalNote: "Add approval context",
    approvalNoteLabel: "Decision context",
    approvalPlaceholder: "Optional approval context. A clear note is required for rejection or a request for more evidence.",
    recording: "Recording approval…",
    alreadyApproved: "Approval already recorded",
    downloadFinalReport: "Download report for review",
    downloadApprovedReport: "Download approved final PDF",
    reviewerRequired: "Reviewer name and role are optional for approval. Blank values use authenticated-operator defaults; test is allowed as reviewer metadata.",
    reviewDownloadRequired: "Download and review this exact report before confirming your review.",
    approvalReady: "Ready to record your approval of this exact report and its disclosed limitations. Outstanding specialist review/QC remains accurately recorded.",
    approvedDownloadNotice: "The exact approved final PDF was downloaded. Client delivery remains separately protected.",
    approvalDownloadFailed: "Approval was recorded, but the approved PDF download failed. Refresh report status, then use Download approved final PDF to retry without approving again.",
    finalReportNotice: "The exact report was downloaded for review. Downloading does not record approval. After reviewing it, use Approve and download final PDF.",
    approveExactReport: "Approve and download final PDF",
    downloadPackage: "Download approved delivery package",
    readyDelivery: "This exact immutable edition and its certified delivery package are approved and client-ready.",
    blockedDelivery: "Client-ready release remains blocked until its legitimate approval and delivery requirements are satisfied.",
    pendingAuthorization: "Approval is recorded for this exact edition. Client delivery remains blocked until its separate requirements and authorization are satisfied.",
    authorizationConfirm: "I reviewed the downloaded APPROVED FINAL PDF and explicitly authorize client delivery of that exact edition and its certified package.",
    authorizeDelivery: "Authorize client delivery",
    authorizingDelivery: "Recording delivery authorization…",
    authorizationNotice: "Client delivery authorization recorded for the exact accepted edition.",
    authorizationFailed: "Unable to authorize client delivery.",
    confirmAuthorizationFirst: "Confirm the separate client-delivery authorization action.",
    defaultAuthorizationReason: "Authorized reviewer reviewed the downloaded APPROVED FINAL PDF and explicitly authorized client delivery of that exact edition and its immutable certified package.",
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
    approvedNotice: "Operator approval recorded and the exact approved final PDF downloaded. Specialist review/QC remains separate. Client delivery remains unauthorized.",
    evidenceNotice: "More evidence requested. Delivery remains blocked. Start a new assessment with the requested evidence; this unchanged report cannot later be approved.",
    rejectedNotice: "Report rejected. Delivery remains blocked.",
    approvalFailed: "Unable to record report approval.",
    decisionFailed: "Unable to record the review decision.",
    pdfMissing: "The completed assessment response did not contain the exact PDF artifact.",
    invalidPdf: "The final assessment PDF failed browser integrity validation.",
    packageMissing: "The approved delivery package is unavailable for this exact run.",
    invalidPackage: "The approved delivery package failed ZIP integrity validation.",
    defaultApprovalReason: "Authorized reviewer confirmed the exact immutable report, scorecard, disclosed evidence limitations, artifact identity, and delivery boundary.",
    reviewerQueue: "Open the exception-first technical review queue for this exact run",
    optionalReviewerMetadata: "Reviewer name and role are optional for approval. Leave them blank or use TEST or test. Use the real operator password, download the exact PDF, and acknowledge its limitations. Optional metadata never counts as specialist review or QC evidence.",
  },
  "es-MX": {
    eyebrow: "NICO COMPREHENSIVE · CONTROL INTERNO DE CALIDAD",
    title: "Aprueba el informe final exacto de la evaluación.",
    lead: "Una evaluación terminada siempre puede producir su informe final exacto. La revisión humana, la aprobación y la entrega al cliente permanecen como estados controlados separados.",
    assessment: "Evaluación",
    comprehensive: "Comprehensive",
    exactRun: "Ejecución exacta",
    identity: "Identidad",
    bound: "Vinculada",
    missing: "Faltante",
    directRun: "Abre esta página desde una evaluación Comprehensive terminada",
    secureAccess: "ACCESO SEGURO",
    identifyReviewer: "Abre la evaluación terminada exacta",
    identityAttached: "La ejecución exacta se vincula automáticamente cuando esta página se abre desde una evaluación terminada. El nombre y la función del revisor son metadatos opcionales; la credencial autenticada del operador es la autoridad de aprobación.",
    reviewer: "Nombre del revisor (opcional)",
    reviewerPlaceholder: "Opcional — vacío usa metadatos del operador autenticado",
    reviewerRole: "Función del revisor (opcional)",
    reviewerRolePlaceholder: "Opcional — escribe test para probar",
    operatorToken: "Contraseña del operador",
    secureToken: "Ingresa tu contraseña de operador de NICO",
    opening: "Abriendo revisión…",
    refresh: "Actualizar revisión",
    open: "Abrir revisión",
    exactIdentity: "Confirmar identidad exacta del informe",
    exactRunId: "ID exacto de ejecución Comprehensive",
    security: "Usa la contraseña privada del operador configurada para NICO en Railway. Permanece únicamente en esta página abierta y nunca se guarda en la URL ni en el almacenamiento del navegador.",
    enterReviewer: "Ingresa el ID exacto de Comprehensive y la contraseña del operador. El nombre y la función del revisor pueden quedar vacíos para aprobar; la entrega al cliente sigue siendo una acción separada y más estricta.",
    loaded: "El paquete inmutable de Comprehensive está cargado. El informe final de evaluación está disponible independientemente de los metadatos opcionales del revisor/cliente.",
    loadFailed: "No fue posible cargar la revisión final.",
    finalDecision: "INFORME FINAL Y ESTADO DE REVISIÓN",
    approveHeading: "Revisa y aprueba el informe exacto de la evaluación",
    approveLead: "Descarga y revisa el informe, confirma ese PDF exacto y después aprueba y descarga el PDF final. El nombre y la función del revisor son metadatos opcionales. Descargar o marcar la casilla no registra la aprobación. La entrega al cliente requiere una autorización separada.",
    review: "Aprobación del informe",
    specialistReview: "Revisión especializada",
    specialistIncomplete: "Sin completar",
    specialistComplete: "Completada",
    operatorDisclosure: "La aprobación del operador acepta este informe exacto con sus limitaciones declaradas y la revisión especializada, el control de calidad independiente y los escalamientos pendientes. No marca ese trabajo como completado ni autoriza la entrega al cliente.",
    delivery: "Lista para el cliente",
    authorized: "Autorizada",
    blocked: "Bloqueada",
    waiting: "Esperando acceso seguro",
    emptyTitle: "Todavía no hay nada más que completar.",
    emptyBody: "Ingresa arriba la ejecución exacta y la contraseña del operador, y abre la evaluación terminada exacta.",
    reviewedExact: "Revisé este informe exacto descargado y lo apruebo con sus limitaciones declaradas y su revisión/QC pendiente.",
    reviewedDetail: "Esto registra la aprobación del operador de esta edición. La revisión especializada, el control de calidad independiente y la entrega al cliente siguen separados.",
    approvalNote: "Agregar contexto de aprobación",
    approvalNoteLabel: "Contexto de la decisión",
    approvalPlaceholder: "Contexto opcional de aprobación. Se requiere una nota clara para rechazar o solicitar más evidencia.",
    recording: "Registrando aprobación…",
    alreadyApproved: "Aprobación ya registrada",
    downloadFinalReport: "Descargar informe para revisión",
    downloadApprovedReport: "Descargar PDF final aprobado",
    reviewerRequired: "El nombre y la función del revisor son opcionales para aprobar. Los valores vacíos usan valores del operador autenticado y test se acepta como metadato de prueba.",
    reviewDownloadRequired: "Descarga y revisa este informe exacto antes de confirmar tu revisión.",
    approvalReady: "Puedes aprobar este informe exacto y sus limitaciones declaradas. La revisión especializada y el control de calidad pendientes permanecerán registrados.",
    approvedDownloadNotice: "Se descargó el PDF final aprobado exacto. La entrega al cliente sigue protegida por separado.",
    approvalDownloadFailed: "La aprobación quedó registrada, pero falló la descarga del PDF aprobado. Actualiza el estado del informe y usa Descargar PDF final aprobado para reintentar sin volver a aprobar.",
    finalReportNotice: "Se descargó el informe exacto para revisión. Descargar no registra la aprobación. Después de revisarlo, usa Aprobar y descargar PDF final.",
    approveExactReport: "Aprobar y descargar PDF final",
    downloadPackage: "Descargar paquete de entrega aprobado",
    readyDelivery: "Esta edición inmutable exacta y su paquete de entrega certificado están aprobados para entrega controlada al cliente.",
    blockedDelivery: "La entrega al cliente permanece bloqueada hasta que se satisfagan sus requisitos legítimos de aprobación y entrega.",
    pendingAuthorization: "La aprobación está registrada para esta edición exacta. La entrega al cliente permanece bloqueada hasta cumplir sus requisitos y autorización separados.",
    authorizationConfirm: "Revisé el PDF FINAL APROBADO descargado y autorizo explícitamente la entrega al cliente de esa edición exacta y su paquete certificado.",
    authorizeDelivery: "Autorizar entrega al cliente",
    authorizingDelivery: "Registrando autorización de entrega…",
    authorizationNotice: "Se registró la autorización de entrega al cliente para la edición aceptada exacta.",
    authorizationFailed: "No fue posible autorizar la entrega al cliente.",
    confirmAuthorizationFirst: "Confirma la acción separada de autorización de entrega al cliente.",
    defaultAuthorizationReason: "El revisor autorizado revisó el PDF FINAL APROBADO descargado y autorizó explícitamente la entrega al cliente de esa edición exacta y su paquete certificado inmutable.",
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
    approvedNotice: "Se registró la aprobación del operador y se descargó el PDF final aprobado exacto. La revisión especializada/QC sigue separada. La entrega al cliente permanece sin autorización.",
    evidenceNotice: "Se solicitó más evidencia. La entrega permanece bloqueada. Inicia una nueva evaluación con la evidencia solicitada; este informe sin cambios no podrá aprobarse después.",
    rejectedNotice: "Informe rechazado. La entrega permanece bloqueada.",
    approvalFailed: "No fue posible registrar la aprobación del informe.",
    decisionFailed: "No fue posible registrar la decisión de revisión.",
    pdfMissing: "La respuesta de la evaluación terminada no contiene el artefacto PDF exacto.",
    invalidPdf: "El PDF final de la evaluación no superó la validación de integridad del navegador.",
    packageMissing: "El paquete de entrega aprobado no está disponible para esta ejecución exacta.",
    invalidPackage: "El paquete de entrega aprobado no superó la validación de integridad ZIP.",
    defaultApprovalReason: "El revisor autorizado confirmó el informe inmutable exacto, la puntuación, las limitaciones de evidencia declaradas, la identidad del artefacto y el límite de entrega.",
    reviewerQueue: "Abrir la cola técnica por excepción para esta ejecución exacta",
    optionalReviewerMetadata: "El nombre y la función del revisor son opcionales para aprobar. Déjalos vacíos o usa TEST o test. Usa la contraseña real del operador, descarga el PDF exacto y reconoce sus limitaciones. Los metadatos opcionales nunca cuentan como evidencia de revisión especializada o QC.",
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

function operatorEditionFrom(value: ReviewResponse | null | undefined): JsonRecord {
  const edition = asRecord(value?.operator_approved_edition);
  const review = asRecord(edition.review);
  return value?.operator_approval_status === "approved"
    && review.decision === "approved"
    && review.approval_basis === "operator_report"
    && /^[0-9a-f]{64}$/i.test(String(review.approval_certificate_sha256 || ""))
    ? edition : {};
}

function acceptedEditionFrom(value: ReviewResponse | null | undefined): JsonRecord {
  if (!value) return {};
  const operatorEdition = operatorEditionFrom(value);
  return Object.keys(operatorEdition).length ? operatorEdition : asRecord(value.accepted_edition || value.review_decision);
}

function reviewCertificateFrom(value: ReviewResponse | null | undefined): JsonRecord {
  const edition = acceptedEditionFrom(value);
  return asRecord(edition.review || value?.review);
}

function reportFrom(value: ReviewResponse | null | undefined): JsonRecord {
  const operatorReports = asRecord(operatorEditionFrom(value).reports);
  return Object.keys(operatorReports).length ? operatorReports : asRecord(value?.reports);
}

function stableIdentity(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableIdentity).join(",")}]`;
  if (value && typeof value === "object") {
    const record = asRecord(value);
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableIdentity(record[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
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
  const code = typeof payload.detail === "string" ? payload.detail : payload.detail?.code;
  if (response.status === 403 && code === "strategic_review_admin_authentication_required") {
    return new Error(locale === "es-MX"
      ? "La contraseña del operador es incorrecta."
      : "The operator password is incorrect.");
  }
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
  const [artifactEdition, setArtifactEdition] = useState<"source" | "es-MX">("source");
  const approvalInFlight = useRef(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale: Locale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setLocale(requestedLocale);
    document.documentElement.lang = requestedLocale;
    setRunId(query.get("run_id") || "");
    setArtifactEdition(query.get("edition") === "es-MX" ? "es-MX" : "source");
  }, []);

  const copy = COPY[locale];
  const operatorReady = Boolean(runId.trim() && adminToken.trim());
  const approvalAuthorityReady = operatorReady;
  const canonicalApprovalReady = Boolean(operatorReady && reviewer.trim() && reviewerRole.trim());
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
  const exactEditionDownloaded = Boolean(
    currentReviewPdfDigest && downloadedArtifactDigest === currentReviewPdfDigest,
  );
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
  const operatorApprovalCompleted = Object.keys(operatorEditionFrom(result)).length > 0;
  const approvalCompleted = operatorApprovalCompleted || rawStatus === "approved" || runStatus === "approved";
  const specialistApprovalCompleted = !operatorApprovalCompleted
    && result?.human_review_completed === true && approvalCompleted;
  const approvalNextStep = !approvalAuthorityReady ? copy.enterReviewer
    : !exactEditionDownloaded ? copy.reviewDownloadRequired
    : !confirmed ? copy.confirmFirst
    : copy.approvalReady;
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

  function editionPath(): string {
    const source = `/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}`;
    return artifactEdition === "source" ? source : `${source}/localized-editions/${artifactEdition}`;
  }

  function statusUrl(): string {
    return canonicalUrl(editionPath());
  }

  function reviewUrl(): string {
    return canonicalUrl(`${editionPath()}/review`);
  }

  function deliveryUrl(): string {
    return canonicalUrl(`${editionPath()}/approved-delivery-package`);
  }

  function deliveryAuthorizationUrl(): string {
    return canonicalUrl(`${editionPath()}/authorize-delivery`);
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
    if (!operatorReady) {
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
    const reason = note;
    const approvalMetadata = {reviewer, reviewerRole};
    return requestJson(reviewUrl(), {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify({
        review_authorized: true,
        authorization_confirmed: true,
        ...(decision === "approved" ? {approval_kind: "operator_report", exact_report_acknowledged: confirmed} : {}),
        reviewer: approvalMetadata.reviewer,
        reviewer_role: approvalMetadata.reviewerRole,
        decision,
        decision_reason: reason,
        expected_artifact_identity: reviewArtifactIdentity,
      }),
    });
  }

  async function prepareLocalizedEdition(): Promise<void> {
    if (!operatorReady || artifactEdition === "source") return;
    setLoading(true);
    setError("");
    setNotice("");
    setResult(null);
    setConfirmed(false);
    setDeliveryConfirmed(false);
    setDownloadedArtifactDigest("");
    try {
      const source = await requestJson(canonicalUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}`), {headers: headers()});
      const prepared = await requestJson(statusUrl(), {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({
          preparation_authorized: true,
          authorization_confirmed: true,
          expected_artifact_identity: asRecord(source.review_artifact_identity),
        }),
      });
      setResult(prepared);
      setNotice(locale === "es-MX"
        ? "Edición en español preparada desde la misma evaluación terminada. La revisión humana y la entrega permanecen separadas."
        : "Spanish edition prepared from the same completed assessment. Human review and delivery remain separate.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.loadFailed);
    } finally {
      setLoading(false);
    }
  }

  async function downloadExactPdf(source: ReviewResponse): Promise<string> {
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
    const editionLabel = artifactEdition === "es-MX" ? "es-MX" : "source";
    // Preserve the server's lifecycle-specific filename; never rename a pending
    // report to FINAL-ASSESSMENT merely because it was downloaded.
    const fallback = `nico-comprehensive-${runId.trim()}-${editionLabel}-REPORT.pdf`;
    const filename = safeFilename(String(exactReport.pdf_filename || ""), fallback);
    return downloadBase64Pdf(
      encoded,
      filename,
      copy.invalidPdf,
      expectedPdfSha256,
    );
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

  async function downloadFinalReport(): Promise<void> {
    if (!operatorReady || !currentReviewPdfDigest || !result) {
      setError(copy.pdfMissing);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const finalReportDigest = await downloadExactPdf(result);
      setDownloadedArtifactDigest(finalReportDigest);
      setNotice(approvalCompleted ? copy.approvedDownloadNotice : copy.finalReportNotice);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : copy.pdfMissing);
    } finally {
      setLoading(false);
    }
  }

  async function approveExactReport(): Promise<void> {
    if (approvalInFlight.current) return;
    if (approvalCompleted) {
      setError(copy.alreadyApproved);
      return;
    }
    if (!approvalAuthorityReady || !confirmed || !exactEditionDownloaded) {
      setError(approvalNextStep);
      return;
    }
    approvalInFlight.current = true;
    setLoading(true);
    setError("");
    setNotice("");
    let approvalRecorded = false;
    try {
      const reviewed = await submitDecision("approved");
      const operatorEdition = operatorEditionFrom(reviewed);
      if (Object.keys(operatorEdition).length
        && stableIdentity(operatorEdition.source_review_artifact_identity) !== stableIdentity(reviewArtifactIdentity)) {
        throw new Error(copy.invalidPdf);
      }
      setResult(reviewed);
      approvalRecorded = reviewCertificateFrom(reviewed).decision === "approved";
      if (!approvalRecorded) throw new Error(copy.approvalFailed);
      setDeliveryConfirmed(false);
      setDownloadedArtifactDigest("");
      const approvedPdfDigest = await downloadExactPdf(reviewed);
      setDownloadedArtifactDigest(approvedPdfDigest);
      setNotice(copy.approvedNotice);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : copy.approvalFailed;
      setError(approvalRecorded ? `${copy.approvalDownloadFailed} ${message}` : message);
    } finally {
      approvalInFlight.current = false;
      setLoading(false);
    }
  }

  async function recordOtherDecision(decision: Decision): Promise<void> {
    if (!canonicalApprovalReady || !note.trim()) {
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
    if (
      !canonicalApprovalReady
      || !specialistApprovalCompleted
      || deliveryAllowed
      || !deliveryConfirmed
      || !currentReviewPdfDigest
      || downloadedArtifactDigest !== currentReviewPdfDigest
    ) {
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

  return <main className={styles.shell} data-review-contract="final-report-independent-v1">
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
        <label>{locale === "es-MX" ? "Edición del informe" : "Report edition"}<select value={artifactEdition} disabled={loading} onChange={(event) => {
          setArtifactEdition(event.target.value === "es-MX" ? "es-MX" : "source");
          setResult(null); setConfirmed(false); setDeliveryConfirmed(false); setDownloadedArtifactDigest(""); setError(""); setNotice("");
        }}>
          <option value="source">{locale === "es-MX" ? "Edición original" : "Source edition"}</option>
          <option value="es-MX">Español (México) — es-MX</option>
        </select></label>
        <label className={styles.reviewerField}>{copy.reviewer}<input value={reviewer} disabled={loading} onChange={(event) => setReviewer(event.target.value)} placeholder={copy.reviewerPlaceholder} autoComplete="name" /></label>
        <label className={styles.tokenField}>{copy.reviewerRole}<input list="nico-reviewer-roles" value={reviewerRole} disabled={loading} onChange={(event) => setReviewerRole(event.target.value)} placeholder={copy.reviewerRolePlaceholder} autoComplete="off" />
          <datalist id="nico-reviewer-roles">
            {AUTHORIZED_REVIEWER_ROLES.map((role) => <option value={role.value} key={role.value}>{locale === "es-MX" ? role.es : role.en}</option>)}
            <option value="test">Test</option>
          </datalist>
        </label>
        <label className={styles.tokenField}>{copy.operatorToken}<input type="password" value={adminToken} disabled={loading} onChange={(event) => setAdminToken(event.target.value)} placeholder={copy.secureToken} autoComplete="current-password" spellCheck={false} /></label>
        <button className={styles.primary} type="submit" disabled={loading || !operatorReady}>{loading ? copy.opening : result ? copy.refresh : copy.open}</button>
        <details className={styles.advanced}><summary>{copy.exactIdentity}</summary><div className={styles.advancedGrid}>
          <label>{copy.assessment}<input value={copy.comprehensive} readOnly aria-readonly="true" /></label>
          <label>{copy.exactRunId}<input value={runId} disabled={loading} onChange={(event) => {setRunId(event.target.value); setResult(null); setConfirmed(false); setDeliveryConfirmed(false); setDownloadedArtifactDigest("");}} placeholder="comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        </div></details>
      </form>
      {artifactEdition === "es-MX" ? <div className={styles.downloadActions}>
        <p>{locale === "es-MX" ? "Prepare la edición en español desde la misma evaluación terminada; no se requiere aprobación humana para generar el informe." : "Prepare the Spanish edition from the same completed assessment; human approval is not required to generate the report."}</p>
        <button className={styles.secondary} type="button" disabled={loading || !operatorReady || Boolean(result)} onClick={prepareLocalizedEdition}>{locale === "es-MX" ? "Preparar informe final en español" : "Prepare Spanish final assessment report"}</button>
      </div> : null}
      <p className={styles.securityNote}>{copy.security}</p>
      <p className={styles.securityNote}>{copy.optionalReviewerMetadata}</p>
      {runId.trim() ? <p className={styles.securityNote}><a href={reviewerQueueHref}>{copy.reviewerQueue}</a></p> : null}
      <div className={styles.feedback} aria-live="polite">{error ? <div className={styles.error} role="alert">{error}</div> : null}{!error && notice ? <div className={styles.success}>{notice}</div> : null}</div>
    </section>

    <section className={`${styles.panel} ${result ? styles.approvalActive : styles.approvalWaiting}`}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>2</span><div><p className={styles.kicker}>{copy.finalDecision}</p><h2>{copy.approveHeading}</h2><p>{copy.approveLead}</p></div></div>
      <p className={styles.securityNote}>{copy.operatorDisclosure}</p>
      <div className={styles.statusGrid}>
        <article className={styles.statusCard}><span>{copy.review}</span><strong>{reviewStatusLabel(rawStatus, locale)}</strong></article>
        <article className={styles.statusCard}><span>{copy.specialistReview}</span><strong>{result?.human_review_completed === true ? copy.specialistComplete : copy.specialistIncomplete}</strong></article>
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
        <label className={styles.confirmRow}><input type="checkbox" checked={confirmed} disabled={!exactEditionDownloaded || loading || approvalCompleted} onChange={(event) => setConfirmed(event.target.checked)} /><span><strong>{copy.reviewedExact}</strong><small>{copy.reviewedDetail}</small></span></label>
        <details className={styles.noteDetails}><summary>{copy.approvalNote}</summary><label>{copy.approvalNoteLabel}<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={copy.approvalPlaceholder} /></label></details>
        <div className={styles.downloadActions}>
          <button className={approvalCompleted ? styles.approve : styles.secondary} type="button" data-nico-pdf-action="true" disabled={loading || !currentReviewPdfDigest} onClick={downloadFinalReport}>{approvalCompleted ? copy.downloadApprovedReport : copy.downloadFinalReport}</button>
          {!approvalCompleted ? <button className={styles.approve} type="button" data-nico-pdf-action="true" aria-describedby="approval-next-step" disabled={loading || !approvalAuthorityReady || !confirmed || !exactEditionDownloaded} onClick={approveExactReport}>{copy.approveExactReport}</button> : null}
          {approvalCompleted ? <span className={styles.securityNote}>{copy.alreadyApproved}</span> : null}
          {deliveryAllowed ? <button className={styles.secondary} type="button" disabled={loading} onClick={downloadPackage}>{copy.downloadPackage}</button> : null}
        </div>
        {!approvalCompleted ? <p id="approval-next-step" className={styles.securityNote} aria-live="polite">{approvalNextStep}</p> : null}
        {specialistApprovalCompleted && !deliveryAllowed ? <label className={styles.confirmRow}><input type="checkbox" checked={deliveryConfirmed} disabled={downloadedArtifactDigest !== currentReviewPdfDigest || !currentReviewPdfDigest} onChange={(event) => setDeliveryConfirmed(event.target.checked)} /><span><strong>{copy.authorizationConfirm}</strong></span></label> : null}
        {specialistApprovalCompleted && !deliveryAllowed ? <div className={styles.downloadActions}><button className={styles.approve} type="button" disabled={loading || !deliveryConfirmed || !canonicalApprovalReady} onClick={authorizeClientDelivery}>{loading ? copy.authorizingDelivery : copy.authorizeDelivery}</button></div> : null}
        <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>{deliveryAllowed ? copy.readyDelivery : approvalCompleted ? copy.pendingAuthorization : copy.blockedDelivery}</div>
        <details className={styles.otherDecisions}><summary>{copy.otherDecision}</summary><p>{copy.otherDecisionLead}</p><div className={styles.decisionActions}><button type="button" disabled={loading || approvalCompleted} onClick={() => recordOtherDecision("request_more_evidence")}>{copy.requestEvidence}</button><button className={styles.reject} type="button" disabled={loading || approvalCompleted} onClick={() => recordOtherDecision("rejected")}>{copy.reject}</button></div></details>
      </>}
    </section>

    {result ? <section className={`${styles.panel} ${styles.recordPanel}`}><details className={styles.record}><summary>{copy.technicalRecord}</summary><pre className={styles.code}>{JSON.stringify({
      status: result.status,
      operator_approval_status: result.operator_approval_status,
      human_review_completed: result.human_review_completed,
      client_delivery_allowed: result.client_delivery_allowed,
      review_artifact_identity: result.review_artifact_identity,
      approval_basis: certificate.approval_basis,
      approval_certificate_sha256: certificateDigest,
      accepted_edition_manifest_sha256: manifestDigest,
      source_review_artifact_identity: edition.source_review_artifact_identity,
      rendering_derivation: edition.rendering_derivation ? {
        version: asRecord(edition.rendering_derivation).version,
        kind: asRecord(edition.rendering_derivation).kind,
        new_human_approval: asRecord(edition.rendering_derivation).new_human_approval,
        authoritative_approval_manifest_sha256: asRecord(edition.rendering_derivation).authoritative_approval_manifest_sha256,
        original_approved_pdf_sha256: asRecord(edition.rendering_derivation).original_approved_pdf_sha256,
      } : undefined,
      report_artifact_digest: reportDigest,
      pdf_filename: report.pdf_filename,
      pdf_sha256: currentReviewPdfDigest,
    }, null, 2)}</pre></details></section> : null}
  </main>;
}
