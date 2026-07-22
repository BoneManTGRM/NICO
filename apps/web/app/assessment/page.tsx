import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";
import AssessmentMetricDisplayV44 from "./AssessmentMetricDisplayV44";

export default function AssessmentPage({locale = "en"}: {locale?: "en" | "es-MX"}) {
  return <>
    <AssessmentRuntimeTruthRepair />
    <AssessmentMetricDisplayV44 />
    <AssessmentWorkspace locale={locale} />
  </>;
}
