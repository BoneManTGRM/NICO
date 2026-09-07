export default function ReviewSessionNotice({runId, locale}: {runId: string; locale: "en" | "es-MX"}) {
  const query = new URLSearchParams({run_id: runId.trim(), lang: locale});
  const returnTo = `/operations/reviewer-queue?${query}`;
  const spanish = locale === "es-MX";
  return <p>
    {spanish ? "Se usa su sesión actual de especialista. " : "Your current specialist session is used. "}
    <a href={`/specialist-login?returnTo=${encodeURIComponent(returnTo)}`}>
      {spanish ? "Iniciar sesión o renovar la sesión" : "Sign in or renew your session"}
    </a>
  </p>;
}
