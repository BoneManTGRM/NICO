const goals = [
  ["Check a repo", "Start Job", "Use this when you want a fast technical health check.", "/start-job"],
  ["Make a client report", "Scanner to Express", "Use this when you need stronger evidence and a PDF report.", "/scanner-workflow"],
  ["Understand the process", "Guided Workflow", "Use this when you are not sure what to click next.", "/guided-workflow"],
  ["Use everything", "Command Center", "Use this only after the simple pages make sense.", "/"],
];

const simpleSteps = [
  ["1", "Start job", "Choose what you are trying to do and save the scope."],
  ["2", "Run scanner when possible", "This gives NICO better dependency, security, and test evidence."],
  ["3", "Run Express", "This creates the maturity score, findings, and PDF."],
  ["4", "Review red/yellow items", "Do not trust a score without reading unavailable evidence."],
  ["5", "Export after review", "Use PDF/Markdown/HTML only after human review."],
];

export default function EasyModePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Easy Mode</p>
        <h1>What do you want to do?</h1>
        <p className="lead">Use this page first. It keeps the main choices simple and sends you to the right NICO workflow.</p>
        <div className="hero-actions">
          <a className="primary-link" href="/start-job">Start job</a>
          <a className="secondary-link" href="/guided-workflow">See guide</a>
          <a className="secondary-link" href="/scanner-workflow">Scanner to Express</a>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Main choices</p><h2>Pick one</h2></div><span className="status green">simple</span></div>
        <div className="results-grid">
          {goals.map(([title, action, note, href]) => (
            <a className="result-card" href={href} key={title}>
              <div className="result-head"><b>{title}</b><span className="status blue">{action}</span></div>
              <p>{note}</p>
            </a>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Simple order</p><h2>Do this, then this</h2></div><span className="status blue">5 steps</span></div>
        <div className="results-grid">
          {simpleSteps.map(([number, title, note]) => (
            <article className="result-card" key={number}>
              <div className="result-head"><b>{number}. {title}</b><span className="status gray">step</span></div>
              <p>{note}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Plain rules</p><h2>How to avoid mistakes</h2></div><span className="status yellow">review required</span></div>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Green does not mean done</p><p>A green score means the evidence looks good. It still needs human review before client delivery.</p></div>
          <div className="mini-panel"><p className="eyebrow">Unavailable is not passed</p><p>If a scanner or data source is unavailable, treat it as missing evidence, not a clean result.</p></div>
          <div className="mini-panel"><p className="eyebrow">Use authorized targets only</p><p>NICO is for defensive assessment of systems you own or are allowed to review.</p></div>
          <div className="mini-panel"><p className="eyebrow">Start simple</p><p>Use Easy Mode and Start Job before the full command center.</p></div>
        </div>
      </section>
    </main>
  );
}
