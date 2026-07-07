const steps = [
  ["1", "Start a job", "Choose the exact job type first so NICO only shows the evidence and actions that matter."],
  ["2", "Confirm authorization", "Enter who authorized the review and the allowed scope. NICO should not run without this."],
  ["3", "Add the repository", "Use owner/repo format. Add client and project names before running scans or reports."],
  ["4", "Collect evidence", "Run Scanner Worker first when possible, then run Express so the report can attach stronger evidence."],
  ["5", "Review findings", "Read red/yellow sections, unavailable evidence, confidence, and human-review warnings before trusting the score."],
  ["6", "Create repairs", "Use Repair Intelligence for suggested fixes. Production changes still require approval and tests."],
  ["7", "Build package", "Generate the client job package only after evidence and findings look correct."],
  ["8", "Export and sign off", "Download PDF/Markdown/HTML/JSON and mark the package client-ready only after human review."],
];

const jobs = [
  ["Quick repo health check", "Run Express only", "Best for a first look or internal check."],
  ["Client Express assessment", "Scanner Worker -> Express -> PDF", "Best for paid audit work and report delivery."],
  ["Repair failed check", "Finding -> Repair suggestion -> approval", "Best when CI, scanner, or report issues need a code fix."],
  ["Retainer project", "Retainer Ops -> reports -> approvals", "Best for ongoing weekly support."],
];

const cards = [
  ["Repository", "Required", "owner/repo or GitHub URL for the authorized target."],
  ["Authorization", "Required", "Who approved the review and what NICO may inspect."],
  ["Scanner result", "Recommended", "Dependency, security, static-analysis, and test/build evidence where tools are available."],
  ["Express result", "Required", "NICO maturity score, sections, findings, unavailable evidence, and PDF output."],
  ["Repair notes", "Optional", "Exact failing symptom, affected files, test plan, and rollback plan."],
  ["Client package", "Final draft", "Scope, evidence, report outline, export links, and human-review status."],
];

export default function GuidedWorkflowPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Guided Workflow</p>
        <h1>Start here</h1>
        <p className="lead">A plain-language path for running NICO without guessing which paste box, endpoint, or report action comes next.</p>
        <div className="hero-actions">
          <a className="primary-link" href="/">Open command center</a>
          <a className="secondary-link" href="/scanner-workflow">Scanner to Express</a>
          <a className="secondary-link" href="#steps">View steps</a>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Choose a job</p><h2>What are you trying to do?</h2></div><span className="status blue">guided</span></div>
        <div className="grid four target-grid">
          {jobs.map(([title, action, note]) => <article key={title}><b>{title}</b><span className="target-number">{action}</span><small>{note}</small></article>)}
        </div>
      </section>

      <section id="steps" className="section panel">
        <div className="section-head"><div><p className="eyebrow">Workflow</p><h2>One clean order</h2></div><span className="status green">8 steps</span></div>
        <div className="results-grid">
          {steps.map(([number, title, note]) => (
            <article className="result-card" key={number}>
              <div className="result-head"><b>{number}. {title}</b><span className="status gray">step</span></div>
              <p>{note}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Evidence cards</p><h2>Replace confusing paste boxes</h2></div><span className="status blue">clear inputs</span></div>
        <div className="results-grid">
          {cards.map(([title, status, note]) => (
            <article className="result-card" key={title}>
              <div className="result-head"><b>{title}</b><span className={status === "Required" ? "status yellow" : "status gray"}>{status}</span></div>
              <p>{note}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Client-ready rule</p><h2>Scores are not the final answer</h2></div><span className="status yellow">human review</span></div>
        <p className="warning-box">A higher score means the evidence looks stronger. It does not remove the requirement for human review, unavailable-evidence review, and final wording approval before client delivery.</p>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Use this first</p><p>For most client work, use Scanner to Express, then review the PDF, then generate repair suggestions only for real findings.</p></div>
          <div className="mini-panel"><p className="eyebrow">Do not skip</p><p>Do not call a report final if scanner evidence is unavailable, authorization is unclear, or the report still has red sections.</p></div>
        </div>
      </section>
    </main>
  );
}
