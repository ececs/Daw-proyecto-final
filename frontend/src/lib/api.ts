/**
 * Axios instance pre-configured for the FastAPI backend.
 *
 * Cross-domain authentication strategy:
 *
 * - The JWT is stored as a readable (non-`HttpOnly`) cookie on the
 *   Vercel domain so the browser can attach it to API calls.
 * - The Next.js edge proxy reads the same cookie server-side for
 *   route protection.
 * - The request interceptor below pulls the token client-side and
 *   sends it as `Authorization: Bearer` to the Railway backend
 *   (different origin). `withCredentials` alone is not enough because
 *   browsers do not share cookies across origins.
 */

import axios from "axios";
import { getAuthToken } from "./auth";

const api = axios.create({
  baseURL: `${process.env.NEXT_PUBLIC_API_URL}/api/v1`,
  withCredentials: true,
  // Why: a 20s timeout absorbs the overhead of dev-mode reloads and
  // concurrent WebSocket activity during local E2E runs without
  // surfacing false-negative timeouts to the user.
  timeout: 20000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Why: attach the Bearer header on every request from the JWT
// readable cookie, since cross-origin cookies are not auto-forwarded.
api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    if (config.headers) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return config;
});

// Why: when the backend returns 401 we route through `/api/auth/clear`
// to drop the HttpOnly session cookie (JS cannot delete it directly),
// breaking the proxy redirect loop a stale cookie would otherwise
// cause before sending the user back to `/login`.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      if (!window.location.pathname.startsWith("/api/auth")) {
        window.location.href = "/api/auth/clear";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
