import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import "../styles/score-assurance.css";
import "../styles/assessment-executive.css";
import "../styles/professional-polish.css";
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
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
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
          <WorkflowCallout>
            <div className="full-run-callout" role="status">
              <b>Assessment workflow:</b> Start Express or Comprehensive from the <a href="/assessment?tier=express#assessment">assessment workspace</a>. Express provides a fast evidence-bound baseline. Comprehensive captures one immutable commit and continues the same native run through repository evidence, scanners, technical and business-context modules, report generation, and required human review. NICO never approves findings or authorizes client delivery automatically. Guidance and authorized operator access are available under <b>More</b>.
            </div>
          </WorkflowCallout>
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
