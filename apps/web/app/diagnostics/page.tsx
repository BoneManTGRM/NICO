export default function DiagnosticsHubPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO hosted diagnostics</p>
        <h1>Diagnostics Hub</h1>
        <p className="lead">Read-only operational checks for scanner runtime support and release-readiness visibility.</p>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Available diagnostics</p>
            <h2>Verification pages</h2>
          </div>
          <span className="status gray">read only</span>
        </div>
        <div className="results-grid">
          <article className="result-card">
            <p className="eyebrow">runtime diagnostics</p>
            <h3>Scanner Runtime Verification</h3>
            <p>Check deployed container tool availability for scanner evidence.</p>
            <a className="primary-link" href="/scanner-runtime">Open scanner runtime</a>
          </article>
          <article className="result-card">
            <p className="eyebrow">readiness diagnostics</p>
            <h3>Release Readiness Verification</h3>
            <p>Check whether release-readiness summary support is installed.</p>
            <a className="primary-link" href="/release-readiness">Open release readiness</a>
          </article>
        </div>
        <p className="warning-box">Diagnostics are evidence-support views only. Human review remains required before client delivery.</p>
      </section>
    </main>
  );
}
