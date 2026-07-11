import type {ReactNode} from "react";
import "../styles/globals.css";
import GenericRepositoryExample from "./GenericRepositoryExample";
import MidAssessmentCompanion from "./MidAssessmentCompanion";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <nav className="global-nav" aria-label="NICO primary navigation">
          <a className="global-brand" href="/easy">NICO</a>
          <div className="global-links">
            <a href="/full-run">Full Assessment</a>
            <a href="/easy">Easy Mode</a>
            <a href="/start-job">Start Job</a>
            <a href="/scanner-workflow">Scanner to Express</a>
            <a href="/refresh-full-evidence">Refresh Evidence</a>
            <a href="/guided-workflow">Guide</a>
            <a href="/">Command Center</a>
          </div>
        </nav>
        <div className="full-run-callout" role="status">
          <b>New:</b> Use the <a href="/">Command Center</a> for the unified Express/Mid intake. Mid keeps one run ID and exact repository snapshot; use <a href="/full-run">Full Assessment</a> for the existing full-run workflow.
        </div>
        <GenericRepositoryExample />
        {children}
        <MidAssessmentCompanion />
      </body>
    </html>
  );
}
