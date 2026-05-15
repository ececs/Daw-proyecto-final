/**
 * Persisted user choice for the AI provider override.
 *
 * The value is read by the chat sidebar and the ticket AI actions to
 * decide which provider to request from the backend. `"auto"` lets
 * the backend pick based on `settings.AI_PROVIDER`.
 */
"use client";

export type AIPreference = "auto" | "openai" | "google";

const STORAGE_KEY = "ai_provider_preference";

/**
 * Read the stored AI preference from `localStorage`.
 *
 * Falls back to `"auto"` on the server (SSR), when the key is unset
 * or when the stored value does not match a known provider.
 */
export function getAIPreference(): AIPreference {
  if (typeof window === "undefined") return "auto";
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (value === "openai" || value === "google" || value === "auto") {
    return value;
  }
  return "auto";
}

/** Persist the AI preference (no-op during SSR). */
export function setAIPreference(value: AIPreference): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, value);
}
