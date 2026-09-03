import type {Metadata} from "next";
import Link from "next/link";
import {
  CLIENT_NAME,
  CUSTOMER_ID,
  NICO_RUN_ID,
  PROJECT_ID,
  PROJECT_NAME,
  REVIEWER,
  REVIEWER_ROLE,
  SARA_COMMIT_SHA,
  SARA_REPOSITORY,
} from "../../api/pilot/sara-finalize/_pilot";
import {
  assertCanonicalReportClear,
  type PilotPreflight,
} from "../../api/pilot/sara-finalize/_truth-v2";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "NICO SARA Pilot · Secure Finalization",
  description: "Protected finalization page for the exact owner-controlled SARA production pilot.",
  robots: {index: false, follow: false, nocache: true},
  referrer: "no-referrer",
};

const ARTIFACT_ROOT = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${NICO_RUN_ID}`;
const DRAFT_PDF = `${ARTIFACT_ROOT}/report/pdf`;
const REPORT_HTML = `${ARTIFACT_ROOT}/report/html`;

export default async function SaraPilotFinalizePage() {
  let preflight: PilotPreflight | null = null;
  let preflightError = "";
  try {
    preflight = await assertCanonicalReportClear();
  } catch (caught) {
    preflightError = caught instanceof Error
      ? caught.message
      : "The live client-delivery identity preflight failed closed.";
  }

  return (
    <main className={styles.shell}>
      <div className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>NICO COMPREHENSIVE · CONTROLLED PILOT</p>
          <h1>Securely finish the verified SARA client report.</h1>
          <p className={styles.lead}>
            This page is hard-bound to one production run, one immutable SARA commit,
            one canonical client, and one canonical project. Approval controls are shown
            only after the live NICO report passes the full client-delivery identity preflight.
          </p>
          <div className={styles.identity}>
            <div><span>Exact run</span><code>{NICO_RUN_ID}</code></div>
            <div><span>Repository</span><strong>{SARA_REPOSITORY}</strong></div>
            <div><span>Immutable SARA commit</span><code>{SARA_COMMIT_SHA}</code></div>
            <div><span>Canonical customer ID</span><code>{CUSTOMER_ID}</code></div>
            <div><span>Canonical project ID</span><code>{PROJECT_ID}</code></div>
            <div><span>Client</span><strong>{CLIENT_NAME}</strong></div>
            <div><span>Project</span><strong>{PROJECT_NAME}</strong></div>
            <div><span>Authorized reviewer</span><strong>{REVIEWER}</strong></div>
            <div><span>Reviewer role</span><strong>{REVIEWER_ROLE}</strong></div>
          </div>
        </section>

        <div className={preflight ? styles.boundary : styles.warning}>
          {preflight ? (
            <>
              LIVE PREFLIGHT PASSED: client identity, project identity, contact, access method,
              authorized scope, immutable SHA, report artifact, zero canonical findings, and zero
              review-required candidates all match the retained production report. Score: {preflight.score}/100.
            </>
          ) : (
            <>
              FINALIZATION BLOCKED: {preflightError} The approval and delivery forms are intentionally hidden.
            </>
          )}
        </div>

        <div className={styles.boundary}>
          The operator password is submitted by HTTPS POST only. It is not placed in the URL,
          cookies, browser storage, source control, or an application database. Each protected
          action discards it after the NICO request finishes.
        </div>

        <section className={styles.panel}>
          <span className={styles.step}>1</span>
          <h2>Review the immutable draft</h2>
          <p>
            Open the exact production report and confirm its scorecard, evidence limitations,
            target SHA, client identity, project identity, and delivery boundary.
          </p>
          <div className={styles.links}>
            <Link className={styles.link} href={DRAFT_PDF} target="_blank" rel="noreferrer">
              Open exact draft PDF
            </Link>
            <Link className={styles.link} href={REPORT_HTML} target="_blank" rel="noreferrer">
              Read exact HTML report
            </Link>
          </div>
        </section>

        {preflight ? (
          <>
            <section className={styles.panel}>
              <span className={styles.step}>2</span>
              <h2>Approve and receive the APPROVED FINAL PDF</h2>
              <p>
                This records human approval against the exact artifact identity returned by NICO.
                The server repeats the live identity and workload checks, submits the immutable
                artifact identity, and verifies the returned PDF signature and SHA-256 digest.
              </p>
              <div className={styles.fixed}>
                <div><span>Reviewer</span><strong>{REVIEWER}</strong></div>
                <div><span>Role</span><strong>{REVIEWER_ROLE}</strong></div>
                <div><span>Draft PDF SHA-256</span><code>{preflight.pdf_sha256}</code></div>
              </div>
              <form className={styles.form} method="post" action="/api/pilot/sara-finalize/approve" autoComplete="off">
                <label className={styles.label}>
                  Current NICO operator password
                  <input
                    className={styles.input}
                    type="password"
                    name="operator_password"
                    required
                    autoComplete="new-password"
                    autoCapitalize="none"
                    spellCheck={false}
                  />
                </label>
                <label className={styles.confirm}>
                  <input type="checkbox" name="confirm_exact_report" value="yes" required />
                  <span>
                    I reviewed the exact draft for run <strong>{NICO_RUN_ID}</strong>, including its
                    scorecard, disclosed evidence limitations, immutable target identity, client and
                    project identity, and delivery boundary.
                  </span>
                </label>
                <button className={styles.button} type="submit">
                  Approve exact report and download APPROVED FINAL PDF
                </button>
              </form>
              <div className={styles.security}>
                A wrong password or any identity, workload, response, PDF, or digest mismatch fails
                closed and does not authorize delivery.
              </div>
            </section>

            <section className={styles.panel}>
              <span className={styles.step}>3</span>
              <h2>Authorize delivery and receive the certified package</h2>
              <p>
                Complete this only after opening and reviewing the APPROVED FINAL PDF from Step 2.
                NICO retains client-delivery authorization as a separate human decision.
              </p>
              <form className={styles.form} method="post" action="/api/pilot/sara-finalize/authorize" autoComplete="off">
                <label className={styles.label}>
                  Current NICO operator password
                  <input
                    className={styles.input}
                    type="password"
                    name="operator_password"
                    required
                    autoComplete="new-password"
                    autoCapitalize="none"
                    spellCheck={false}
                  />
                </label>
                <label className={styles.confirm}>
                  <input type="checkbox" name="confirm_approved_pdf" value="yes" required />
                  <span>
                    I reviewed the downloaded APPROVED FINAL PDF and explicitly authorize client
                    delivery of that exact edition and its immutable certified package.
                  </span>
                </label>
                <button className={`${styles.button} ${styles.buttonDanger}`} type="submit">
                  Authorize client delivery and download certified package
                </button>
              </form>
              <div className={styles.warning}>
                Do not use this step before reviewing the approved PDF. Approval and delivery
                authorization intentionally remain two distinct human decisions.
              </div>
            </section>
          </>
        ) : null}

        <p className={styles.footer}>
          Owner-controlled SARA production pilot. This page cannot target another run,
          repository, commit, client, project, reviewer, or reviewer role.
        </p>
      </div>
    </main>
  );
}
