"use client";

export type AIPreference = "auto" | "openai" | "google";

const STORAGE_KEY = "ai_provider_preference";

export function getAIPreference(): AIPreference {
  if (typeof window === "undefined") return "auto";
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (value === "openai" || value === "google" || value === "auto") {
    return value;
  }
  return "auto";
}

export function setAIPreference(value: AIPreference): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, value);
}
