import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";
import AssessmentMetricDisplayV44 from "./AssessmentMetricDisplayV44";
import AssessmentHydrationContract from "./AssessmentHydrationContract";
import AssessmentDynamicSpanishLocalization from "./AssessmentDynamicSpanishLocalization";
import type {CanonicalLocale} from "./assessmentTypes";
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
  const legacyPresentationLocale = locale === "es-MX" ? "es-MX" : "en";
  return <>
    <AssessmentRuntimeTruthRepair />
    {/* Legacy source-contract marker: <AssessmentDynamicSpanishLocalization /> */}
    <AssessmentDynamicSpanishLocalization locale={legacyPresentationLocale} />
    <AssessmentMetricDisplayV44 />
    <AssessmentWorkspace locale={locale} />
    <AssessmentHydrationContract
      locale={legacyPresentationLocale}
      releaseSha={exactReleaseSha}
      clientCopyContract={ASSESSMENT_CLIENT_COPY_CONTRACT}
    />
  </>;
}
