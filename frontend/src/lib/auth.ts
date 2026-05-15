/**
 * Client-side helpers for reading the auth token from cookies.
 */

/**
 * Return the JWT stored in the readable `access_token` cookie, or
 * `null` when running on the server or when no cookie is present.
 *
 * The cookie is set by the Next.js auth callback and consumed by
 * the axios request interceptor (`lib/api.ts`).
 */
export function getAuthToken(): string | null {
  if (typeof document === "undefined") return null;

  const tokenMatch = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
  if (!tokenMatch) return null;

  try {
    return decodeURIComponent(tokenMatch[1]);
  } catch (err) {
    console.error("Failed to decode auth token", err);
    return null;
  }
}
