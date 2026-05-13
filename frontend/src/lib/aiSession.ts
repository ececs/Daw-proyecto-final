/**
 * Per-tab AI session timestamp. Stored in sessionStorage so it persists across
 * page navigations and panel open/close, but resets when the tab is closed or
 * the user logs out (we clear it explicitly in the logout handler).
 *
 * Used by the AI status panel to scope session-usage stats to the current
 * browser session (instead of the process-global, multi-worker-inconsistent
 * counters that lived in backend memory).
 */

const KEY = "ai_session_start";

export function getAISessionStart(): string {
  if (typeof window === "undefined") return new Date().toISOString();
  let value = sessionStorage.getItem(KEY);
  if (!value) {
    value = new Date().toISOString();
    sessionStorage.setItem(KEY, value);
  }
  return value;
}

export function resetAISessionStart(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(KEY);
}
