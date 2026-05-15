/**
 * Dashboard layout — shared chrome for every authenticated route.
 *
 * Server Component that reads the `access_token` cookie via
 * `cookies()` and forwards it as a string prop to the client-side
 * `DashboardHeader`. The Header needs the raw token to build the
 * WebSocket URL because browser JS cannot read the `HttpOnly`
 * cookie directly, and `EventSource` / `WebSocket` cannot carry
 * custom headers.
 *
 * The exposure risk is contained: the token only exists in memory
 * on the client side (never rendered in HTML) and the same value
 * already travels over the WebSocket URL anyway.
 *
 * `AuthInitializer` is mounted once here so the Zustand auth store
 * is hydrated for every descendant client component.
 */

import { cookies } from "next/headers";
import { DashboardHeader } from "@/components/layout/DashboardHeader";
import { AuthInitializer } from "@/components/layout/AuthInitializer";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value ?? null;

  return (
    <div className="min-h-screen bg-slate-50">
      <AuthInitializer />
      <DashboardHeader token={token} />
      <main className="max-w-7xl mx-auto">{children}</main>
    </div>
  );
}
