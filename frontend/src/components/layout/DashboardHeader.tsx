/**
 * `DashboardHeader` — top navigation bar shared by every authenticated
 * page.
 *
 * Hosts the app logo, the AI assistant toggle, the AI status pop-up,
 * the notification bell with its real-time badge, and the user
 * dropdown (profile + sign-out). Also bootstraps the WebSocket
 * connection (`useWebSocket`) and the initial notifications fetch
 * (`useNotifications`) so they live once at the layout level rather
 * than in every page.
 *
 * The JWT travels from the Server Component layout as a string prop
 * because the `HttpOnly` cookie cannot be read by browser JS but is
 * required by the WebSocket URL.
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogOut, Bot } from "lucide-react";
import useAuthStore from "@/stores/authStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { useNotifications } from "@/hooks/useNotifications";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ChatSidebar } from "@/components/ai-chat/ChatSidebar";
import { AIStatusButton } from "@/components/ai/AIStatusPanel";
import { useUIStore } from "@/hooks/useUIStore";
import api from "@/lib/api";

interface DashboardHeaderProps {
  /** JWT token forwarded from the server cookie (for the WebSocket auth URL) */
  token: string | null;
}

export function DashboardHeader({ token }: DashboardHeaderProps) {
  const router = useRouter();
  const { user } = useAuthStore();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const { isChatOpen: chatOpen, setChatOpen } = useUIStore();

  // Why: hook handles `null` internally, so calling unconditionally
  // keeps the rules-of-hooks happy and only opens a socket once `token`
  // is hydrated by the auth store.
  useWebSocket(token);

  useNotifications();

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Why: backend may be unreachable; the client-side cleanup below
      // is enough to sign the user out of this tab.
    }
    // Why: the demo login flow does not roundtrip through the OAuth
    // callback, so we cannot rely on the server to clear the cookie.
    document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT;";

    const { resetAISessionStart } = await import("@/lib/aiSession");
    resetAISessionStart();

    // Why: hard reload to drop any in-memory Zustand state and force
    // the proxy to re-evaluate route protection on the next request.
    router.push("/login");
    window.location.reload();
  };

  return (
    <>
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white px-3 py-3 sm:px-6">
      <div className="mx-auto flex max-w-7xl min-w-0 items-center justify-between gap-2">
        <Link href="/board" className="min-w-0 truncate font-bold text-base tracking-tight text-slate-800 transition-colors hover:text-blue-600 sm:text-lg">
          D4-Ticket{" "}
          <span className="text-blue-600">AI</span>
        </Link>

        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <button
            onClick={() => setChatOpen(!chatOpen)}
            className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-medium transition-colors sm:h-auto sm:w-auto sm:gap-1.5 sm:px-3 sm:py-1.5 ${
              chatOpen
                ? "bg-blue-600 text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            }`}
            aria-label="Toggle AI assistant"
          >
            <Bot className="w-4 h-4" />
            <span className="hidden sm:block">AI</span>
          </button>

          <AIStatusButton />

          <NotificationBell />

          <div className="relative">
            <button
              onClick={() => setDropdownOpen((o) => !o)}
              className="flex items-center gap-2 rounded-lg p-1.5 transition-colors hover:bg-slate-100"
              aria-label="User menu"
            >
              <UserAvatar 
                src={user?.avatar_url} 
                name={user?.name || "User"} 
                size="sm" 
              />
              <span className="text-sm text-slate-700 hidden sm:block max-w-[140px] truncate">
                {user?.name}
              </span>
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  aria-hidden
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-xl shadow-lg border border-slate-200 z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-100">
                    <p className="text-sm font-medium text-slate-800 truncate">{user?.name}</p>
                    <p className="text-xs text-slate-400 truncate">{user?.email}</p>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>

    {/* Why: render the chat outside the header so its overlay does
        not get clipped by the sticky `<header>` z-index stacking. */}
    {chatOpen && <ChatSidebar onClose={() => setChatOpen(false)} />}
  </>
  );
}
