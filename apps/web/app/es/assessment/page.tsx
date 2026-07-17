import AssessmentPage from "../../assessment/page";
import SpanishAssessmentLocalization from "./SpanishAssessmentLocalization";

export const metadata = {
  title: "Evaluaciones NICO",
  description: "Evaluaciones técnicas NICO Express, Intermedia y Completa vinculadas a evidencia.",
};

export default function SpanishAssessmentPage() {
  return (
    <>
      <SpanishAssessmentLocalization />
      <AssessmentPage />
    </>
  );
}
