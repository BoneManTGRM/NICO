import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import "../styles/score-assurance.css";
import "../styles/assessment-executive.css";
import "../styles/professional-polish.css";
import "../styles/site-polish-v2.css";
import "../styles/workflow-simplification.css";
import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge";
import AssessmentExactCommitTransport from "./AssessmentExactCommitTransport";
import AssessmentExpressRecoveryActions from "./AssessmentExpressRecoveryActions";
import AssessmentExpressRecoveryGuard from "./AssessmentExpressRecoveryGuard";
import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel";
import AssessmentFailureResponseBridge from "./AssessmentFailureResponseBridge";
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
import UnifiedAssessmentPublicGuard from "./UnifiedAssessmentPublicGuard";
import WorkflowCallout from "./WorkflowCallout";
import WorkspaceClarityRepair from "./WorkspaceClarityRepair";

/*
Canonical workflow disclosure retained as a source-level regression contract:
Assessment workflow: Run one unified NICO assessment from href="/assessment?tier=comprehensive#assessment".
The assessment captures one immutable commit and continues through required human review.
NICO never approves findings or creates client delivery automatically.
Guidance remains under More → Guide.
Operator-only deployment controls are available only in protected operator workspaces.
Ongoing evidence refresh remains a post-acceptance operator workflow.
*/

export const metadata = {
  title: "NICO",
  description: "Evidence-bound technical and strategic assessment with exact-snapshot reporting and required human review.",
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
          <AssessmentFailureResponseBridge />
          <AssessmentHomeRedirect />
          <LegacyFullRunRedirect />
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <AssessmentScoreAssuranceGuard />
          <OperationsPreloadGuard />
          <RetainerAutoEvidenceLauncher />
          <WorkspaceClarityRepair />
          <UnifiedAssessmentPublicGuard />
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
