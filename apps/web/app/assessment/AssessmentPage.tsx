import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";
import AssessmentHydrationContract from "./AssessmentHydrationContract";
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

export default function AssessmentPage({locale = "en"}: {locale?: "en" | "es-MX"}) {
  const exactReleaseSha = releaseSha();
  return <>
    <AssessmentRuntimeTruthRepair />
    <AssessmentHydrationContract
      locale={locale}
      releaseSha={exactReleaseSha}
      clientCopyContract={ASSESSMENT_CLIENT_COPY_CONTRACT}
    />
    <AssessmentWorkspace locale={locale} />
  </>;
}
