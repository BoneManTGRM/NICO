import AssessmentPage from "../../assessment/page";
import SpanishDocumentLanguage from "./SpanishDocumentLanguage";

export const metadata = {
  title: "NICO Comprehensive",
  description: "NICO Comprehensive en español, vinculado a evidencia.",
};

export default function SpanishAssessmentPage() {
  return <>
    <SpanishDocumentLanguage />
    <AssessmentPage locale="es-MX" />
  </>;
}
