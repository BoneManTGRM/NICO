const goals = [
  ["Check a repo", "Run Express", "Use this for a fast authorized technical health check.", "/assessment?tier=express#assessment"],
  ["Run a deeper assessment", "Run Mid or Full", "Use this when you need durable run identity, scanner stages, and formal review.", "/assessment?tier=mid#assessment"],
  ["Understand the process", "Guided Workflow", "Use this when you are not sure what happens after the assessment starts.", "/guided-workflow"],
  ["Operate NICO", "Operations", "Use this for authenticated deployment, recovery, reliability, and alert evidence.", "/operations"],
];

const simpleSteps = [
  ["1", "Choose Express, Mid, or Full", "Use the tier selector on the single Run a Job page."],
  ["2", "Enter the repository once", "Client and project names are optional report labels."],
  ["3", "Confirm authorization", "Use the checkbox only for a repository you own or have explicit permission to assess."],
  ["4", "Run and wait for the exact result", "Do not start a duplicate Mid or Full run while the same run is active or recoverable."],
  ["5", "Review before export", "Read findings and unavailable evidence, then complete required human review."],
];

export default function EasyModePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Easy Mode</p>
        <h1>What do you want to do?</h1>
        <p className="lead">Use one assessment intake for Express, Mid, and Full. Advanced tools remain separate for operators and recovery.</p>
        <div className="hero-actions">
          <a className="primary-link" href="/assessment?tier=express#assessment">Run a Job</a>
          <a className="secondary-link" href="/guided-workflow">See guide</a>
          <a className="secondary-link" href="/operations">Operations</a>
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
          <div className="mini-panel"><p className="eyebrow">Green does not mean done</p><p>A green score means the available evidence looks good. It still needs human review before client delivery.</p></div>
          <div className="mini-panel"><p className="eyebrow">Unavailable is not passed</p><p>If a scanner or data source is unavailable, treat it as missing evidence, not a clean result.</p></div>
          <div className="mini-panel"><p className="eyebrow">Use authorized targets only</p><p>NICO is for defensive assessment of systems you own or are allowed to review.</p></div>
          <div className="mini-panel"><p className="eyebrow">Enter facts once</p><p>Use Run a Job as the normal intake. Do not repeat repository and authorization details in a separate setup wizard.</p></div>
        </div>
      </section>
    </main>
  );
}
