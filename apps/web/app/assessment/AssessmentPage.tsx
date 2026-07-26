import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";

export default function AssessmentPage({locale = "en"}: {locale?: "en" | "es-MX"}) {
  return <>
    <AssessmentRuntimeTruthRepair />
    <AssessmentWorkspace locale={locale} />
  </>;
}
