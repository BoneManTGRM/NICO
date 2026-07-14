import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import AssessmentHomeRedirect from "./AssessmentHomeRedirect";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import GenericRepositoryExample from "./GenericRepositoryExample";
import LegacyFullRunRedirect from "./LegacyFullRunRedirect";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import {MidWorkspaceProvider} from "./MidWorkspaceContext";
import OperationsPreloadGuard from "./OperationsPreloadGuard";
import PrimaryNavigation from "./PrimaryNavigation";
import ReportPresentationGuard from "./ReportPresentationGuard";
import RetainerAutoEvidenceLauncher from "./RetainerAutoEvidenceLauncher";
import UnifiedMidTokenCapture from "./UnifiedMidTokenCapture";
import WorkflowCallout from "./WorkflowCallout";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <MidWorkspaceProvider>
          <AssessmentHomeRedirect />
          <LegacyFullRunRedirect />
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <OperationsPreloadGuard />
          <UnifiedMidTokenCapture />
          <RetainerAutoEvidenceLauncher />
          <PrimaryNavigation />
          <WorkflowCallout />
          <GenericRepositoryExample />
          {children}
          <MidAssessmentCompanion />
          <MidEvidencePacketHelper />
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
