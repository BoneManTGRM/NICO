"use client";

import styles from "./engagementFieldStateControls.module.css";
import type {Locale} from "./assessmentTypes";
import {
  engagementFieldStateLabel,
  type EngagementFieldState,
} from "./engagementFieldState";

export default function EngagementFieldStateControls({
  locale,
  state,
  disabled,
  onChange,
}: {
  locale: Locale;
  state: EngagementFieldState;
  disabled?: boolean;
  onChange: (state: EngagementFieldState) => void;
}) {
  const unavailable = state === "excluded_from_scope" || state === "not_applicable";
  const copy = locale === "es-MX"
    ? {
        state: "Estado",
        exclude: "Excluir del alcance",
        notApplicable: "No aplica",
        clear: "Quitar selección",
      }
    : {
        state: "State",
        exclude: "Exclude from scope",
        notApplicable: "Not applicable",
        clear: "Clear selection",
      };

  return <div className={styles.controls} data-engagement-state={state}>
    <span className={`${styles.status} ${unavailable ? styles.explicit : ""}`}>
      {copy.state}: {engagementFieldStateLabel(state, locale)}
    </span>
    <span className={styles.actions}>
      {unavailable ? <button
        type="button"
        disabled={disabled}
        onClick={() => onChange("not_supplied")}
      >
        {copy.clear}
      </button> : <>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange("excluded_from_scope")}
        >
          {copy.exclude}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange("not_applicable")}
        >
          {copy.notApplicable}
        </button>
      </>}
    </span>
  </div>;
}
