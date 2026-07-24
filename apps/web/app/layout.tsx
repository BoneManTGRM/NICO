import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import "../styles/score-assurance.css";
import "../styles/assessment-executive.css";
import "../styles/professional-polish.css";
import "../styles/site-polish-v2.css";
import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge";
import AssessmentExactCommitTransport from "./AssessmentExactCommitTransport";
import AssessmentExpressRecoveryActions from "./AssessmentExpressRecoveryActions";
import AssessmentExpressRecoveryGuard from "./AssessmentExpressRecoveryGuard";
import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel";
import AssessmentFinalGateAuthoritativeGuard from "./AssessmentFinalGateAuthoritativeGuard";
import AssessmentHomeRedirect from "./AssessmentHomeRedirect";
import AssessmentProgressIntegrityGuard from "./AssessmentProgressIntegrityGuard";
import AssessmentRecoveryActions from "./AssessmentRecoveryActions";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import AssessmentRunStateGuard from "./AssessmentRunStateGuard";
import AssessmentScoreAssuranceGuard from "./AssessmentScoreAssuranceGuard";
import AssessmentStatusOutcomeGuard from "./AssessmentStatusOutcomeGuard";
import AssessmentStatusResilience from "./AssessmentStatusResilience";
import GenericRepositoryExample from "./GenericRepositoryExample";
import LegacyFullRunRedirect from "./LegacyFullRunRedirect";
import {MidWorkspaceProvider} from "./MidWorkspaceContext";
import OperationsPreloadGuard from "./OperationsPreloadGuard";
import PrimaryNavigation from "./PrimaryNavigation";
import ReportPresentationGuard from "./ReportPresentationGuard";
import RetainerAutoEvidenceLauncher from "./RetainerAutoEvidenceLauncher";
import WorkflowCallout from "./WorkflowCallout";
import WorkspaceClarityRepair from "./WorkspaceClarityRepair";

export const metadata = {
  title: "NICO",
  description: "Evidence-bound technical health assessments with exact-snapshot reporting and required human review.",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="nico-app">
        <MidWorkspaceProvider>
          <AssessmentRunStateGuard />
          <AssessmentStatusResilience />
          <AssessmentStatusOutcomeGuard />
          <AssessmentExpressRecoveryGuard />
          <AssessmentProgressIntegrityGuard />
          <AssessmentFinalGateAuthoritativeGuard />
          <AssessmentApiTransportBridge />
          <AssessmentExactCommitTransport />
          <AssessmentHomeRedirect />
          <LegacyFullRunRedirect />
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <AssessmentScoreAssuranceGuard />
          <OperationsPreloadGuard />
          <RetainerAutoEvidenceLauncher />
          <WorkspaceClarityRepair />
          <PrimaryNavigation />
          <WorkflowCallout />
          <GenericRepositoryExample />
          <AssessmentFailureEvidencePanel />
          <AssessmentExpressRecoveryActions />
          <AssessmentRecoveryActions />
          {children}
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
