/**
 * Auth callback route — sets the `access_token` cookie.
 *
 * Called by:
 *
 * - The FastAPI OAuth callback after a successful Google login,
 *   redirecting here with `?token=<jwt>`.
 * - The login page's demo-login flow, which forwards the JWT
 *   returned by `/auth/demo-login` through this route so the cookie
 *   is set with the same attributes regardless of entry point.
 *
 * The cookie is **not** `HttpOnly` because the axios client needs to
 * read it to populate the `Authorization: Bearer` header sent to the
 * Railway backend (different origin — browsers do not share cookies
 * across origins). The Next.js edge proxy also consumes the same
 * cookie to gate authenticated routes.
 */

import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token");

  if (!token) {
    return NextResponse.redirect(new URL("/login?error=missing_token", request.url));
  }

  const response = NextResponse.redirect(new URL("/board", request.url));

  const maxAge = 60 * 60 * 24 * 7; // 7 days
  response.cookies.set("access_token", token, {
    httpOnly: false,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge,
    path: "/",
  });

  return response;
}
