from pathlib import Path

path = Path("apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match, got {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
    '    identityAttached: "The exact run is attached automatically when this page is opened from a completed assessment. Reviewer identity is optional for report generation and is used only for separate review/approval actions.",\n'
    '    reviewer: "Authorized reviewer",\n'
    '    reviewerPlaceholder: "Optional unless recording human approval",\n'
    '    reviewerRole: "Reviewer role",\n'
    '    reviewerRolePlaceholder: "Optional unless recording human approval",',
    '    identityAttached: "The exact run is attached automatically when this page is opened from a completed assessment. Reviewer name and role are optional metadata; the authenticated operator credential is the approval authority.",\n'
    '    reviewer: "Reviewer name (optional)",\n'
    '    reviewerPlaceholder: "Optional — blank uses authenticated operator metadata",\n'
    '    reviewerRole: "Reviewer role (optional)",\n'
    '    reviewerRolePlaceholder: "Optional — type test when testing",',
)
replace_once(
    '    enterReviewer: "Enter the exact Comprehensive run ID and operator password. Reviewer identity is required only for separate human approval or a client-delivery decision.",',
    '    enterReviewer: "Enter the exact Comprehensive run ID and operator password. Reviewer name and role may be blank for approval; client delivery remains a separate, stricter action.",',
)
replace_once(
    '    approveLead: "Download and review the report, enter your reviewer name and role in Step 1, then approve and download the final PDF. A download or checked box alone does not record approval. Client delivery is a separate authorization.",',
    '    approveLead: "Download and review the report, confirm that exact PDF, then approve and download the final PDF. Reviewer name and role are optional metadata. A download or checked box alone does not record approval. Client delivery is a separate authorization.",',
)
replace_once(
    '    reviewerRequired: "Enter your reviewer name and select your authorized role in Step 1. These are required for approval, not for downloading the report.",',
    '    reviewerRequired: "Reviewer name and role are optional for approval. Blank values use authenticated-operator defaults; test is allowed as reviewer metadata.",',
)
replace_once(
    '    reviewerQueue: "Open the exception-first technical review queue for this exact run",',
    '    reviewerQueue: "Open the exception-first technical review queue for this exact run",\n'
    '    optionalReviewerMetadata: "Reviewer name and role are optional for approval. Leave them blank or use test while testing. The operator password must still be valid, the exact PDF must be downloaded and acknowledged, and all server-side review/QC gates still apply.",',
)

replace_once(
    '    identityAttached: "La ejecución exacta se vincula automáticamente cuando esta página se abre desde una evaluación terminada. La identidad del revisor es opcional para generar el informe y solo se usa en acciones separadas de revisión/aprobación.",\n'
    '    reviewer: "Revisor autorizado",\n'
    '    reviewerPlaceholder: "Opcional salvo para registrar aprobación humana",\n'
    '    reviewerRole: "Función del revisor",\n'
    '    reviewerRolePlaceholder: "Opcional salvo para registrar aprobación humana",',
    '    identityAttached: "La ejecución exacta se vincula automáticamente cuando esta página se abre desde una evaluación terminada. El nombre y la función del revisor son metadatos opcionales; la credencial autenticada del operador es la autoridad de aprobación.",\n'
    '    reviewer: "Nombre del revisor (opcional)",\n'
    '    reviewerPlaceholder: "Opcional — vacío usa metadatos del operador autenticado",\n'
    '    reviewerRole: "Función del revisor (opcional)",\n'
    '    reviewerRolePlaceholder: "Opcional — escribe test para probar",',
)
replace_once(
    '    enterReviewer: "Ingresa el ID exacto de Comprehensive y la contraseña del operador. La identidad del revisor se requiere solo para una aprobación humana separada o una decisión de entrega al cliente.",',
    '    enterReviewer: "Ingresa el ID exacto de Comprehensive y la contraseña del operador. El nombre y la función del revisor pueden quedar vacíos para aprobar; la entrega al cliente sigue siendo una acción separada y más estricta.",',
)
replace_once(
    '    approveLead: "Descarga y revisa el informe, ingresa tu nombre y función de revisor en el paso 1 y después aprueba y descarga el PDF final. Descargar o marcar la casilla no registra la aprobación. La entrega al cliente requiere una autorización separada.",',
    '    approveLead: "Descarga y revisa el informe, confirma ese PDF exacto y después aprueba y descarga el PDF final. El nombre y la función del revisor son metadatos opcionales. Descargar o marcar la casilla no registra la aprobación. La entrega al cliente requiere una autorización separada.",',
)
replace_once(
    '    reviewerRequired: "Ingresa tu nombre de revisor y selecciona tu función autorizada en el paso 1. Son necesarios para aprobar, no para descargar el informe.",',
    '    reviewerRequired: "El nombre y la función del revisor son opcionales para aprobar. Los valores vacíos usan valores del operador autenticado y test se acepta como metadato de prueba.",',
)
replace_once(
    '    reviewerQueue: "Abrir la cola técnica por excepción para esta ejecución exacta",',
    '    reviewerQueue: "Abrir la cola técnica por excepción para esta ejecución exacta",\n'
    '    optionalReviewerMetadata: "El nombre y la función del revisor son opcionales para aprobar. Déjalos vacíos o usa test durante las pruebas. La contraseña del operador debe seguir siendo válida, debes descargar y reconocer el PDF exacto y todos los controles de revisión/QC del servidor siguen aplicando.",',
)

replace_once(
    '  const operatorReady = Boolean(runId.trim() && adminToken.trim());\n'
    '  const canonicalApprovalReady = Boolean(operatorReady && reviewer.trim() && reviewerRole.trim());',
    '  const operatorReady = Boolean(runId.trim() && adminToken.trim());\n'
    '  const approvalAuthorityReady = operatorReady;\n'
    '  const canonicalApprovalReady = Boolean(operatorReady && reviewer.trim() && reviewerRole.trim());',
)
replace_once(
    '  const approvalNextStep = !operatorReady ? copy.enterReviewer\n'
    '    : !canonicalApprovalReady ? copy.reviewerRequired\n'
    '    : !exactEditionDownloaded ? copy.reviewDownloadRequired\n'
    '    : !confirmed ? copy.confirmFirst\n'
    '    : copy.approvalReady;',
    '  const approvalNextStep = !approvalAuthorityReady ? copy.enterReviewer\n'
    '    : !exactEditionDownloaded ? copy.reviewDownloadRequired\n'
    '    : !confirmed ? copy.confirmFirst\n'
    '    : copy.approvalReady;',
)

replace_once(
    '  async function submitDecision(decision: "approved" | Decision): Promise<ReviewResponse> {\n'
    '    const reason = decision === "approved"\n'
    '      ? note.trim() || copy.defaultApprovalReason\n'
    '      : note.trim();',
    '  function approvalReviewerMetadata(): {reviewer: string; reviewerRole: string} {\n'
    '    const suppliedReviewer = reviewer.trim();\n'
    '    const suppliedRole = reviewerRole.trim();\n'
    '    const canonicalRole = AUTHORIZED_REVIEWER_ROLES.find(\n'
    '      (role) => role.value.toLowerCase() === suppliedRole.toLowerCase(),\n'
    '    )?.value;\n'
    '    return {\n'
    '      reviewer: suppliedReviewer || "Authenticated NICO operator",\n'
    '      reviewerRole: canonicalRole || (!suppliedRole || suppliedRole.toLowerCase() === "test"\n'
    '        ? "Security reviewer"\n'
    '        : suppliedRole),\n'
    '    };\n'
    '  }\n\n'
    '  async function submitDecision(decision: "approved" | Decision): Promise<ReviewResponse> {\n'
    '    const reason = decision === "approved"\n'
    '      ? note.trim() || copy.defaultApprovalReason\n'
    '      : note.trim();\n'
    '    const approvalMetadata = decision === "approved"\n'
    '      ? approvalReviewerMetadata()\n'
    '      : {reviewer: reviewer.trim(), reviewerRole: reviewerRole.trim()};',
)
replace_once(
    '        reviewer: reviewer.trim(),\n        reviewer_role: reviewerRole.trim(),',
    '        reviewer: approvalMetadata.reviewer,\n        reviewer_role: approvalMetadata.reviewerRole,',
)
replace_once(
    '    if (!canonicalApprovalReady || !confirmed || !exactEditionDownloaded) {',
    '    if (!approvalAuthorityReady || !confirmed || !exactEditionDownloaded) {',
)

replace_once(
    '        <label className={styles.tokenField}>{copy.reviewerRole}<select value={reviewerRole} disabled={loading} onChange={(event) => setReviewerRole(event.target.value)}>\n'
    '          <option value="">{copy.reviewerRolePlaceholder}</option>\n'
    '          {AUTHORIZED_REVIEWER_ROLES.map((role) => <option value={role.value} key={role.value}>{locale === "es-MX" ? role.es : role.en}</option>)}\n'
    '        </select></label>',
    '        <label className={styles.tokenField}>{copy.reviewerRole}<input list="nico-reviewer-roles" value={reviewerRole} disabled={loading} onChange={(event) => setReviewerRole(event.target.value)} placeholder={copy.reviewerRolePlaceholder} autoComplete="off" />\n'
    '          <datalist id="nico-reviewer-roles">\n'
    '            {AUTHORIZED_REVIEWER_ROLES.map((role) => <option value={role.value} key={role.value}>{locale === "es-MX" ? role.es : role.en}</option>)}\n'
    '            <option value="test">Test</option>\n'
    '          </datalist>\n'
    '        </label>',
)
replace_once(
    '      <p className={styles.securityNote}>{copy.security}</p>',
    '      <p className={styles.securityNote}>{copy.security}</p>\n'
    '      <p className={styles.securityNote}>{copy.optionalReviewerMetadata}</p>',
)
replace_once(
    'disabled={loading || !canonicalApprovalReady || !confirmed || !exactEditionDownloaded} onClick={approveExactReport}',
    'disabled={loading || !approvalAuthorityReady || !confirmed || !exactEditionDownloaded} onClick={approveExactReport}',
)
replace_once(
    'disabled={loading || !deliveryConfirmed} onClick={authorizeClientDelivery}',
    'disabled={loading || !deliveryConfirmed || !canonicalApprovalReady} onClick={authorizeClientDelivery}',
)

path.write_text(text, encoding="utf-8")
print("patched", path)
