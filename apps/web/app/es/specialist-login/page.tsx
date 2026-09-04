"use client";

import {FormEvent, useEffect, useState} from "react";

const DESTINATION = "/es/assessment?tier=comprehensive#assessment";

export default function SpanishSpecialistLoginPage() {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.documentElement.lang = "es-MX";
    void fetch("/api/nico/operator-session", {method: "GET", cache: "no-store"}).then((response) => {
      if (response.ok) window.location.replace(DESTINATION);
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
        setError(response.status === 403 ? "La contraseña del operador de NICO no fue aceptada." : "El acceso seguro para especialistas no está disponible.");
        return;
      }
      setPassword("");
      window.location.assign(DESTINATION);
    } catch {
      setError("El acceso seguro para especialistas no está disponible.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero-card">
      <p className="eyebrow">NICO COMPREHENSIVE</p>
      <h1>Acceso para especialistas en ciberseguridad</h1>
      <p>Inicia sesión con la contraseña privada del operador de NICO. La admisión, el estado de las ejecuciones, los artefactos, la aprobación y la entrega permanecen inaccesibles sin una sesión autenticada.</p>
      <form onSubmit={submit} className="result-card">
        <label htmlFor="nico-operator-password"><b>Contraseña del operador</b></label>
        <input
          id="nico-operator-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          maxLength={4096}
          required
        />
        <button type="submit" disabled={loading || !password.trim()}>{loading ? "Iniciando sesión…" : "Abrir NICO"}</button>
        {error ? <p role="alert">{error}</p> : null}
      </form>
      <p className="muted">La contraseña se intercambia una sola vez por una cookie de sesión firmada, de duración limitada, HttpOnly y SameSite=Strict. No se guarda en la URL ni en el almacenamiento del navegador.</p>
      <p className="muted"><a href="/specialist-login">English</a></p>
    </section>
  </main>;
}
