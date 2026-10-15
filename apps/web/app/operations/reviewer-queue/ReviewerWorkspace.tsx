"use client";

import {useEffect, useRef, useState} from "react";
import ReviewerQueue from "./ReviewerQueue";
import ReviewQueueBrowser from "./ReviewQueueBrowser";
import ReviewWorkPanel from "./ReviewWorkPanel";
import styles from "./reviewer-queue.module.css";

export default function ReviewerWorkspace() {
  const [runId, setRunId] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [spanish, setSpanish] = useState(false);
  const selected = useRef("");
  function select(value: string) {
    selected.current = value.trim();
    setRunId(value.trim());
    setRefresh(0);
    const url = new URL(window.location.href);
    if (value.trim()) url.searchParams.set("run_id", value.trim()); else url.searchParams.delete("run_id");
    try {window.history.replaceState(window.history.state, "", url.href);} catch { /* Visible selection remains authoritative. */ }
  }
  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    select(params.get("run_id") || "");
    setSpanish(params.get("lang") === "es-MX");
  }, []);
  const props = {runId, refresh, isCurrent: () => selected.current === runId,
    onChanged: (changedRunId: string) => {if (selected.current === changedRunId) setRefresh(value => value + 1);}};
  return <>
    <section className={styles.panel}>
      <label>{spanish ? "Ejecución seleccionada para todo el espacio de revisión" : "Selected run for the entire review workspace"}
        <input value={runId} onChange={event => select(event.target.value)} autoComplete="off" spellCheck={false} />
      </label>
    </section>
    <ReviewerQueue key={`queue:${runId}`} {...props} />
    <ReviewQueueBrowser key={`browser:${runId}`} {...props} />
    <ReviewWorkPanel key={`work:${runId}`} {...props} />
  </>;
}
