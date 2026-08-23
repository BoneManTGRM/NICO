import AssessmentPage from "../../assessment/AssessmentPage";
import SpanishDocumentLanguage from "./SpanishDocumentLanguage";

export const metadata = {
  title: "Evaluaciones NICO — Comprehensive",
  description: "NICO Comprehensive en español, vinculado a evidencia.",
};

export default function SpanishAssessmentPage() {
  return <>
    <SpanishDocumentLanguage />
    <AssessmentPage locale="es-MX" />
  </>;
}
