const assessmentServices = [
  {
    id: "express",
    name: "NICO Express Technical Assessment",
    purpose: "Fast, evidence-bound technical baseline and prioritized risk report.",
    bestFor: "Founders, investors, and teams that need a rapid technical diagnosis.",
    includes: [
      "Repository, dependency, security, static-analysis, CI/CD, architecture, complexity, and velocity evidence",
      "Decision-oriented executive report and ranked priority actions",
      "Exact-snapshot traceability and human-review-bound delivery",
    ],
  },
  {
    id: "comprehensive",
    name: "NICO Comprehensive Technical Assessment",
    purpose: "Complete technical diligence, QA, operating-model, roadmap, and resourcing assessment.",
    bestFor: "Organizations that need the former Mid and Full scope as one premium assessment.",
    includes: [
      "Everything in Express with deeper scanner execution and evidence triage",
      "Functional QA, platform parity, deployment, infrastructure, and delivery-process review",
      "Stakeholder alignment, requirements traceability, six-month roadmap, staffing, and sequencing",
      "One snapshot, one run ID, one evidence ledger, one final human-reviewed client package",
    ],
  },
];

const comprehensiveStages = [
  "Core technical scan",
  "Deep evidence analysis",
  "Functional QA and platform parity",
  "Deployment and infrastructure review",
  "Stakeholder and business alignment",
  "Developer delivery-process analysis",
  "Six-month roadmap and resourcing",
  "Human review and final delivery",
];

export default function ServicesPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO service model</p>
        <h1>Two assessment services. One clear decision.</h1>
        <p className="lead">
          Choose Express for a rapid technical baseline or Comprehensive for complete technical diligence.
          Legacy Mid and Full execution profiles remain supported internally but are no longer separate customer products.
        </p>
        <div className="hero-actions">
          <a href="/#assessment" className="primary-link">Run an assessment</a>
          <a href="/" className="secondary-link">Return to command center</a>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div><p className="eyebrow">Assessment catalog</p><h2>Express + Comprehensive</h2></div>
          <span className="status blue">Human review required</span>
        </div>
        <div className="grid two">
          {assessmentServices.map((service) => (
            <article key={service.id} className="mini-panel">
              <p className="eyebrow">{service.id.toUpperCase()}</p>
              <h2>{service.name}</h2>
              <p>{service.purpose}</p>
              <p><b>Best for:</b> {service.bestFor}</p>
              <h3>Included</h3>
              <ul className="tight-list">{service.includes.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div><p className="eyebrow">Comprehensive workflow</p><h2>One premium assessment behind one simple intake</h2></div>
          <span className="status gray">One snapshot · one run ID</span>
        </div>
        <ol className="tight-list">{comprehensiveStages.map((stage) => <li key={stage}>{stage}</li>)}</ol>
        <p className="warning-box">
          NICO Monitor + Execute remains a recurring operational service. It is not a third assessment tier and does not bypass authorization, approval, testing, or delivery controls.
        </p>
      </section>
    </main>
  );
}
