import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";
import AssessmentMetricDisplayV44 from "./AssessmentMetricDisplayV44";
import AssessmentHydrationContract from "./AssessmentHydrationContract";
import AssessmentDynamicSpanishLocalization from "./AssessmentDynamicSpanishLocalization";
import AssessmentProviderParityBridge from "./AssessmentProviderParityBridge";
import AssessmentIntakeDomSnapshotBridge from "./AssessmentIntakeDomSnapshotBridge";
import type {CanonicalLocale, Locale} from "./assessmentTypes";
import "./assessment-inline-readiness.css";

export const ASSESSMENT_CLIENT_COPY_CONTRACT = "expert-engagement-hydrated-v1";

function releaseSha(): string {
  return String(
    process.env.VERCEL_GIT_COMMIT_SHA
      || process.env.NICO_RELEASE_SHA
      || process.env.GITHUB_SHA
      || "unknown",
  ).trim();
}

export default function AssessmentPage({locale = "en-US"}: {locale?: CanonicalLocale}) {
  const exactReleaseSha = releaseSha();
  const presentationLocale: Locale = locale === "es-MX" ? "es-MX" : "en";
  const clientApprovalGuidance = presentationLocale === "es-MX"
    ? "Para la aprobación final y la entrega protegida al cliente, complete Cliente, Proyecto, método de acceso, contacto técnico principal y alcance autorizado, y confirme la autorización. Una admisión de navegador completa y autorizada recibe alcance de cliente vinculado a la ejecución; una admisión incompleta o no confirmada permanece interna y no puede aprobarse para entrega."
    : "For final approval and protected client delivery, complete Client, Project, access method, primary technical contact, and authorized scope, then confirm authorization. A complete authorized browser intake receives run-bound client scope; incomplete or unconfirmed intake remains internal and cannot be approved for delivery.";
  const operatorIntakeLabel = presentationLocale === "es-MX"
    ? "Usar admisión de operador autorizado para acceso de proveedor controlado o alcance preasignado"
    : "Use Authorized operator intake for operator-controlled provider access or preassigned scope";
  return <>
    <AssessmentRuntimeTruthRepair />
    {/* Legacy source-contract marker: <AssessmentDynamicSpanishLocalization /> */}
    <AssessmentDynamicSpanishLocalization locale={presentationLocale} />
    <AssessmentMetricDisplayV44 />
    <AssessmentProviderParityBridge locale={presentationLocale} />
    <AssessmentIntakeDomSnapshotBridge />
    <div className="shell" data-assessment-client-approval-guidance="true">
      <p className="warning-box">
        {clientApprovalGuidance}{" "}
        <a href="/operations/provider-intake">{operatorIntakeLabel}</a>
      </p>
    </div>
    <AssessmentWorkspace locale={presentationLocale} />
    <AssessmentHydrationContract
      locale={presentationLocale}
      releaseSha={exactReleaseSha}
      clientCopyContract={ASSESSMENT_CLIENT_COPY_CONTRACT}
    />
  </>;
}
