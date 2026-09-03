import type {Metadata} from "next";
import Link from "next/link";
import {
  NICO_RUN_ID,
  REVIEWER,
  REVIEWER_ROLE,
  SARA_COMMIT_SHA,
} from "../../api/pilot/sara-finalize/_lib";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "NICO SARA Pilot · Secure Finalization",
  description: "Temporary branch-only operator page for the exact retained SARA pilot run.",
  robots: {index: false, follow: false, nocache: true},
  referrer: "no-referrer",
};

const ARTIFACT_ROOT = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${NICO_RUN_ID}`;
const DRAFT_PDF = `${ARTIFACT_ROOT}/report/pdf`;
const REPORT_HTML = `${ARTIFACT_ROOT}/report/html`;

export default function SaraPilotFinalizePage() {
  return (
    <main className={styles.shell}>
      <div className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>NICO COMPREHENSIVE · CONTROLLED PILOT</p>
          <h1>Securely finish the exact SARA report.</h1>
          <p className={styles.lead}>
            This temporary branch-only page bypasses the mobile browser fetch failure without changing
            NICO&apos;s production release or weakening its approval gates. It is hard-bound to one retained
            run and one immutable SARA commit.
          </p>
          <div className={styles.identity}>
            <div><span>Exact run</span><code>{NICO_RUN_ID}</code></div>
            <div><span>Immutable SARA commit</span><code>{SARA_COMMIT_SHA}</code></div>
            <div><span>Authorized reviewer</span><strong>{REVIEWER}</strong></div>
            <div><span>Reviewer role</span><strong>{REVIEWER_ROLE}</strong></div>
          </div>
        </section>

        <div className={styles.boundary}>
          The operator password is submitted by HTTPS POST only. This helper does not put it in the URL,
          cookies, browser storage, source control, or an application database. Each action discards it
          after the protected NICO request finishes.
        </div>

        <section className={styles.panel}>
          <span className={styles.step}>1</span>
          <h2>Review the immutable draft</h2>
          <p>
            Open the exact report first. Confirm its scorecard, findings, evidence limitations, target SHA,
            and delivery boundary before approving anything.
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

        <section className={styles.panel}>
          <span className={styles.step}>2</span>
          <h2>Approve and receive the APPROVED FINAL PDF</h2>
          <p>
            This records the human approval against the exact artifact identity returned by NICO. The
            server verifies the retained run, immutable SARA SHA, zero unresolved technical-review work,
            PDF signature, and SHA-256 digest before returning the approved final PDF.
          </p>
          <div className={styles.fixed}>
            <div><span>Reviewer</span><strong>{REVIEWER}</strong></div>
            <div><span>Role</span><strong>{REVIEWER_ROLE}</strong></div>
          </div>
          <form className={styles.form} method="post" action="/api/pilot/sara-finalize/approve" autoComplete="off">
            <label className={styles.label}>
              Temporary or current NICO operator password
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
                I reviewed the exact draft report for run <strong>{NICO_RUN_ID}</strong>, including its
                scorecard, disclosed evidence limitations, immutable target identity, and delivery boundary.
              </span>
            </label>
            <button className={styles.button} type="submit">
              Approve exact report and download APPROVED FINAL PDF
            </button>
          </form>
          <div className={styles.security}>
            A wrong password or any identity, workload, response, PDF, or digest mismatch fails closed and
            does not authorize delivery.
          </div>
        </section>

        <section className={styles.panel}>
          <span className={styles.step}>3</span>
          <h2>Authorize delivery and receive the certified package</h2>
          <p>
            Complete this only after opening and reviewing the APPROVED FINAL PDF downloaded in Step 2.
            NICO retains this as a separate client-delivery authorization.
          </p>
          <form className={styles.form} method="post" action="/api/pilot/sara-finalize/authorize" autoComplete="off">
            <label className={styles.label}>
              Temporary or current NICO operator password
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
                I reviewed the downloaded APPROVED FINAL PDF and explicitly authorize client delivery of
                that exact edition and its immutable certified package.
              </span>
            </label>
            <button className={`${styles.button} ${styles.buttonDanger}`} type="submit">
              Authorize client delivery and download certified package
            </button>
          </form>
          <div className={styles.warning}>
            Do not use this step before reviewing the approved PDF. Approval and delivery authorization
            intentionally remain two distinct human decisions.
          </div>
        </section>

        <p className={styles.footer}>
          Temporary operational bridge for the owner-controlled SARA pilot. It cannot target another run,
          repository, commit, reviewer, or reviewer role.
        </p>
      </div>
    </main>
  );
}
