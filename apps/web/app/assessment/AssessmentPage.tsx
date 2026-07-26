import AssessmentWorkspace from "./AssessmentWorkspace";
import AssessmentRuntimeTruthRepair from "./AssessmentRuntimeTruthRepair";
import "./assessment-inline-readiness.css";

export default function AssessmentPage({locale = "en"}: {locale?: "en" | "es-MX"}) {
  return <>
    <AssessmentRuntimeTruthRepair />
    <AssessmentWorkspace locale={locale} />
  </>;
}
