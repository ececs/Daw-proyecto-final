/**
 * Per-tab AI session timestamp.
 *
 * Stored in `sessionStorage` so it survives navigation and the AI
 * panel toggling but resets when the tab closes or the user logs out
 * (cleared explicitly by the logout handler).
 *
 * The timestamp is sent as a `since=` filter to `GET /ai/status` so
 * the panel shows usage scoped to the current browser session,
 * sidestepping the process-global counters that would otherwise be
 * inconsistent across uvicorn workers.
 */

const KEY = "ai_session_start";

/**
 * Return the start ISO timestamp of the current AI session, creating
 * one on the first call. Falls back to `now` during SSR.
 */
export function getAISessionStart(): string {
  if (typeof window === "undefined") return new Date().toISOString();
  let value = sessionStorage.getItem(KEY);
  if (!value) {
    value = new Date().toISOString();
    sessionStorage.setItem(KEY, value);
  }
  return value;
}

/** Drop the cached session start so the next read creates a fresh one. */
export function resetAISessionStart(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(KEY);
}
