/**
 * Next.js edge proxy — route protection.
 *
 * In Next.js 16 the old `middleware.ts` convention was renamed to
 * `proxy.ts`; the auth-guard behaviour is unchanged.
 *
 * Rules:
 *
 * - **Public paths** (`/login`, `/api/auth/*`, `/_next/*`) are
 *   accessible without a token.
 * - Every other route requires the `access_token` cookie. A missing
 *   cookie redirects to `/login?next=<pathname>` so the original
 *   destination is preserved.
 * - Visiting `/login` while already authenticated redirects to
 *   `/board` so the user is not stuck on the sign-in screen.
 *
 * The proxy only checks **cookie presence** — fast and DB-free.
 * Token validity is verified by FastAPI on every API call.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth", "/_next"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("access_token")?.value;

  const isPublicPath = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (!isPublicPath && !token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (pathname === "/login" && token) {
    return NextResponse.redirect(new URL("/board", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
