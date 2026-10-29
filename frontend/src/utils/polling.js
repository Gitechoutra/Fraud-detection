/**
 * How often screens that show new alerts re-read them. The specification
 * asks for new alerts on screen within 3 seconds: a held or blocked payment's
 * alert is saved together with its decision, so it appears at the latest one
 * interval later. backend evaluator.ALERT_POLL_MS uses the same value when it
 * measures this -- keep the two equal.
 */
export const ALERT_POLL_MS = 2000;

/** Dashboard KPIs (open alerts, held, blocked): inside the same 3 seconds. */
export const DASHBOARD_POLL_MS = 3000;

/** Dashboard charts change slowly and cost more to compute. */
export const CHART_POLL_MS = 15000;
