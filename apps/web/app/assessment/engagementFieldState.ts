import type {Locale} from "./assessmentTypes";

export const ENGAGEMENT_FIELD_KEYS = [
  "client_name",
  "project_name",
  "primary_technical_contact",
  "access_method",
  "authorized_scope",
] as const;

export type EngagementFieldKey = (typeof ENGAGEMENT_FIELD_KEYS)[number];
export type EngagementFieldState =
  | "supplied_verified"
  | "supplied_unverified"
  | "not_supplied"
  | "excluded_from_scope"
  | "not_applicable";

export type EngagementFieldStateRecord = {
  state: EngagementFieldState;
  value: string | null;
  source: string;
  excluded_by?: string;
  excluded_at?: string;
  reason?: string;
};

export type EngagementFieldStates = Record<
  EngagementFieldKey,
  EngagementFieldStateRecord
>;

const VALID_STATES = new Set<EngagementFieldState>([
  "supplied_verified",
  "supplied_unverified",
  "not_supplied",
  "excluded_from_scope",
  "not_applicable",
]);

export function engagementFieldStateLabel(
  state: EngagementFieldState,
  locale: Locale,
): string {
  const labels: Record<EngagementFieldState, Record<Locale, string>> = {
    supplied_verified: {en: "Verified", "es-MX": "Verificado"},
    supplied_unverified: {
      en: "Supplied — independent verification pending",
      "es-MX": "Proporcionado — verificación independiente pendiente",
    },
    not_supplied: {en: "Not supplied", "es-MX": "No proporcionado"},
    excluded_from_scope: {
      en: "Excluded from scope",
      "es-MX": "Excluido del alcance",
    },
    not_applicable: {en: "Not applicable", "es-MX": "No aplica"},
  };
  return labels[state][locale];
}

function recordForValue(value: string): EngagementFieldStateRecord {
  return value.trim()
    ? {
        state: "supplied_unverified",
        value,
        source: "client_supplied_intake",
      }
    : {state: "not_supplied", value: null, source: "intake"};
}

export function emptyEngagementFieldStates(): EngagementFieldStates {
  return Object.fromEntries(
    ENGAGEMENT_FIELD_KEYS.map((field) => [field, recordForValue("")]),
  ) as EngagementFieldStates;
}

export function engagementValues(
  clientName: string,
  projectName: string,
  primaryTechnicalContact: string,
  accessMethod: string,
  authorizedScope: string,
): Record<EngagementFieldKey, string> {
  return {
    client_name: clientName,
    project_name: projectName,
    primary_technical_contact: primaryTechnicalContact,
    access_method: accessMethod,
    authorized_scope: authorizedScope,
  };
}

export function normalizeEngagementFieldStates(
  value: unknown,
  values: Record<EngagementFieldKey, string>,
): EngagementFieldStates {
  const source = value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
  const output = emptyEngagementFieldStates();
  for (const field of ENGAGEMENT_FIELD_KEYS) {
    const raw = source[field] && typeof source[field] === "object"
      && !Array.isArray(source[field])
      ? (source[field] as Record<string, unknown>)
      : {};
    const candidate = String(raw.state || "") as EngagementFieldState;
    const state = VALID_STATES.has(candidate)
      ? candidate
      : values[field]
        ? "supplied_unverified"
        : "not_supplied";
    const supplied = state === "supplied_verified" || state === "supplied_unverified";
    if (supplied !== Boolean(values[field].trim())) {
      output[field] = recordForValue(values[field]);
      continue;
    }
    output[field] = {
      state,
      value: supplied ? values[field] : null,
      source: String(raw.source || (supplied ? "client_supplied_intake" : "intake")),
      ...(raw.excluded_by ? {excluded_by: String(raw.excluded_by)} : {}),
      ...(raw.excluded_at ? {excluded_at: String(raw.excluded_at)} : {}),
      ...(raw.reason ? {reason: String(raw.reason)} : {}),
    };
  }
  return output;
}

export function withEngagementValue(
  states: EngagementFieldStates,
  field: EngagementFieldKey,
  value: string,
): EngagementFieldStates {
  return {...states, [field]: recordForValue(value)};
}

export function withEngagementState(
  states: EngagementFieldStates,
  field: EngagementFieldKey,
  state: EngagementFieldState,
  currentValue: string,
): EngagementFieldStates {
  const supplied = state === "supplied_verified" || state === "supplied_unverified";
  return {
    ...states,
    [field]: supplied
      ? {...recordForValue(currentValue), state}
      : {
          state,
          value: null,
          source: state === "not_supplied" ? "intake" : "user_action",
        },
  };
}

export function isEngagementFieldUnavailable(state: EngagementFieldState): boolean {
  return state === "excluded_from_scope" || state === "not_applicable";
}
