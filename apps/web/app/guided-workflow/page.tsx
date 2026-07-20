const steps = [
  ["1", "Open Run a Job", "Use the unified assessment page instead of completing a separate setup wizard."],
  ["2", "Choose Express or Comprehensive", "Select the service that matches the evidence depth and review you need."],
  ["3", "Enter the authorized repository", "Use owner/repo or a GitHub URL. Client and project names are optional."],
  ["4", "Confirm authorization and run", "Use the single authorization checkbox, then start the selected assessment once."],
  ["5", "Review evidence and findings", "Read unavailable evidence, confidence, findings, and human-review warnings before trusting the score."],
  ["6", "Review and export", "Download draft artifacts only after the exact run and report wording have been reviewed by a human."],
];

const jobs = [
  ["Quick repo health check", "Run Express", "Best for a first look or internal technical baseline."],
  ["Complete technical diligence", "Run Comprehensive", "Best for one immutable snapshot, deeper technical and business-context modules, and formal review."],
  ["Repair failed check", "Use exact failure evidence", "Best when CI, scanner, or report issues need a bounded repair PR."],
  ["Retainer project", "Use Retainer Ops", "Best for ongoing weekly evidence and commercial support."],
];

const cards = [
  ["Repository", "Required", "owner/repo or GitHub URL for the authorized target."],
  ["Client and project", "Optional", "Useful report labels that do not change authorization or evidence."],
  ["Authorization checkbox", "Required", "Confirms ownership or explicit permission for the selected target."],
  ["Assessment service", "Required", "Express or Comprehensive selected on the same intake page."],
  ["Run identity", "Retained", "Use the exact returned run ID for continuation, recovery, report, and review."],
  ["Draft report", "Human review", "Scores and exports remain review-required and are not automatically client-ready."],
];

export default function GuidedWorkflowPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Guided Workflow</p>
        <h1>One assessment intake</h1>
        <p className="lead">Start Express or Comprehensive from one page without duplicating repository details or authorization fields.</p>
        <div className="hero-actions">
          <a className="primary-link" href="/assessment?tier=express#assessment">Run a Job</a>
          <a className="secondary-link" href="/scanner-workflow">Scanner tools</a>
          <a className="secondary-link" href="#steps">View steps</a>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Choose a workflow</p><h2>What are you trying to do?</h2></div><span className="status blue">guided</span></div>
        <div className="grid four target-grid">
          {jobs.map(([title, action, note]) => <article key={title}><b>{title}</b><span className="target-number">{action}</span><small>{note}</small></article>)}
        </div>
      </section>

      <section id="steps" className="section panel">
        <div className="section-head"><div><p className="eyebrow">Workflow</p><h2>One clean order</h2></div><span className="status green">6 steps</span></div>
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
        <div className="section-head"><div><p className="eyebrow">Unified inputs</p><h2>Enter each fact once</h2></div><span className="status blue">lower error risk</span></div>
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
        <p className="warning-box">A higher score means the available evidence looks stronger. It does not remove unavailable-evidence review, exact-run verification, or final wording approval before client delivery.</p>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Normal path</p><p>Use Run a Job, select Express or Comprehensive, enter the repository once, confirm authorization, and review the returned evidence-bound draft.</p></div>
          <div className="mini-panel"><p className="eyebrow">Advanced tools</p><p>Use Operations, Recovery, Scanner tools, and Retainer only when the assessment or operator workflow specifically requires them.</p></div>
        </div>
      </section>
    </main>
  );
}
