import AssessmentWorkspace from "./AssessmentWorkspace";

export default function AssessmentPage({locale = "en"}: {locale?: "en" | "es-MX"}) {
  return <AssessmentWorkspace locale={locale} />;
}
