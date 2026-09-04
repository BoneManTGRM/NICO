"use client";

import {FormEvent, useEffect, useState} from "react";

const ENGLISH_DESTINATION = "/assessment?tier=comprehensive#assessment";
const SPANISH_DESTINATION = "/es/assessment?tier=comprehensive#assessment";

function safeDestination(): string {
  const requested = new URLSearchParams(window.location.search).get("next");
  return requested === SPANISH_DESTINATION
    ? SPANISH_DESTINATION
    : ENGLISH_DESTINATION;
}

export default function SpecialistLoginPage() {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/nico/operator-session", {method: "GET", cache: "no-store"}).then((response) => {
      if (response.ok) window.location.replace(safeDestination());
    });
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/nico/operator-session", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password}),
        cache: "no-store",
      });
      if (!response.ok) {
        setError(response.status === 403 ? "The NICO operator password was not accepted." : "Secure specialist access is unavailable.");
        return;
      }
      setPassword("");
      window.location.assign(safeDestination());
    } catch {
      setError("Secure specialist access is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero-card">
      <p className="eyebrow">NICO COMPREHENSIVE</p>
      <h1>Cybersecurity specialist access</h1>
      <p>Sign in with the private NICO operator password. Assessment intake, exact-run status, review artifacts, approval, and delivery remain inaccessible without an authenticated session.</p>
      <form onSubmit={submit} className="result-card">
        <label htmlFor="nico-operator-password"><b>Operator password</b></label>
        <input
          id="nico-operator-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          maxLength={4096}
          required
        />
        <button type="submit" disabled={loading || !password.trim()}>{loading ? "Signing in…" : "Open NICO"}</button>
        {error ? <p role="alert">{error}</p> : null}
      </form>
      <p className="muted">The password is exchanged once for a signed, short-lived, HttpOnly session cookie. It is not stored in the URL or browser storage.</p>
    </section>
  </main>;
}
