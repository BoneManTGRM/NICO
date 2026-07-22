import AssessmentPage from "../../assessment/page";
import SpanishDocumentLanguage from "./SpanishDocumentLanguage";

export const metadata = {
  title: "Evaluaciones NICO",
  description: "Evaluaciones técnicas NICO Express e Integral vinculadas a evidencia.",
};

export default function SpanishAssessmentPage() {
  return <>
    <SpanishDocumentLanguage />
    <AssessmentPage locale="es-MX" />
  </>;
}
