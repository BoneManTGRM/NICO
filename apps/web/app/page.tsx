const quickStartCommands = `pip install -r requirements.txt
python -m nico scan-test-lab
python -m nico assess local nico/test_lab --authorized
python -m nico assess report latest --format markdown
python -m nico assess verify latest`;

const assessmentCommands = `python -m nico assess local /path/to/project --authorized
python -m nico assess github owner/repo --authorized
python -m nico assess archive ./project.zip --authorized
python -m nico assess url https://staging.example.com --passive-only --authorized
python -m nico assess report latest --format markdown
python -m nico assess verify latest`;

const safetyRules = [
  "Defensive-only",
  "Authorized systems only",
  "No exploitation",
  "No brute force",
  "No authentication bypass",
  "No credential theft",
  "No destructive actions",
];

const assessmentAreas = [
  "Code Audit",
  "Dependency / Library Ecosystem",
  "Secrets Exposure Review",
  "CI/CD Analysis",
  "Architecture & Technical Debt",
  "Passive URL Review, if used",
  "Bug-Risk Findings",
  "Repair Recommendations",
  "Verification Checklist",
  "Markdown / HTML Reports",
];

export default function Page() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO No-Server Command Center</p>
        <h1>Authorized bug assessment without a hosted backend</h1>
        <p className="lead">
          NICO is ready for local-first defensive assessments from the CLI. The hosted site is a guide and status page until a backend is intentionally deployed later.
        </p>
        <div className="hero-actions">
          <a href="#commands" className="primary-link">Copy commands</a>
          <a href="#safety" className="secondary-link">Safety boundary</a>
        </div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">System Status</p>
            <h2>Current operating mode</h2>
          </div>
          <span className="status green">Server required: no</span>
        </div>
        <div className="grid three">
          <article><b>Current Mode</b><span>No-Server CLI Assessment</span></article>
          <article><b>Backend</b><span>Optional Later</span></article>
          <article><b>Testing Path</b><span>Local CLI / authorized repo / archive / passive URL</span></article>
        </div>
        <p className="warning-box">
          Browser mode cannot scan local files without a backend or local app. Real testing currently runs from the local CLI on systems you own or are explicitly authorized to assess.
        </p>
      </section>

      <section id="commands" className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">How to test now</p>
            <h2>Run NICO from your local CLI</h2>
          </div>
          <span className="status blue">No server</span>
        </div>
        <p className="muted">
          Use these commands on your computer or Codespace. The <code>--authorized</code> flag confirms that you own the target or have explicit permission to assess it.
        </p>
        <div className="command-grid">
          <div className="command-card">
            <b>First test with NICO test lab</b>
            <textarea readOnly defaultValue={quickStartCommands} aria-label="NICO quick start commands" />
          </div>
          <div className="command-card">
            <b>Assess your authorized systems</b>
            <textarea readOnly defaultValue={assessmentCommands} aria-label="NICO no-server assessment commands" />
          </div>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Assessment Scope</p>
            <h2>What the no-server engine checks</h2>
          </div>
          <span className="status gray">Evidence-bound</span>
        </div>
        <div className="scope-grid">
          {assessmentAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}
        </div>
      </section>

      <section id="safety" className="section two-col">
        <div className="panel">
          <p className="eyebrow">Safety Boundary</p>
          <h2>Allowed use</h2>
          <p className="muted">
            NICO is for defensive assessments of systems you own or are explicitly authorized to assess. It should not be used to scan unrelated internet targets.
          </p>
          <ul className="tight-list">
            {safetyRules.map((rule) => <li key={rule}>{rule}</li>)}
          </ul>
        </div>
        <div className="panel">
          <p className="eyebrow">Truth Rules</p>
          <h2>No fake findings</h2>
          <ul className="tight-list">
            <li>No fake backend status.</li>
            <li>No fake scan results.</li>
            <li>No placeholder findings.</li>
            <li>No invented vulnerabilities.</li>
            <li>Missing tools are reported as unavailable.</li>
            <li>Scores must cite scanned files, visible passive evidence, command output, or unavailable-data notes.</li>
          </ul>
        </div>
      </section>

      <section className="section panel">
        <details>
          <summary>
            <span>
              <p className="eyebrow">Optional Hosted Backend Later</p>
              <h2>Backend health checking is not required now</h2>
            </span>
            <span className="status gray">Optional</span>
          </summary>
          <div className="details-body">
            <p className="muted">
              When a hosted dashboard is intentionally deployed, Vercel can point to a backend with <code>NEXT_PUBLIC_NICO_API_URL</code>. Until then, app.nicoaudit.com should not claim that browser-based assessments are running.
            </p>
            <div className="grid two">
              <article><b>Frontend</b><span>https://app.nicoaudit.com</span></article>
              <article><b>Backend</b><span>Not required for no-server CLI mode</span></article>
            </div>
            <pre className="code-block">NEXT_PUBLIC_NICO_API_URL=https://YOUR-NICO-API-HOST
NICO_CORS_ORIGINS=https://app.nicoaudit.com,https://nicoaudit.vercel.app</pre>
          </div>
        </details>
      </section>
    </main>
  );
}
