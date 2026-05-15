/**
 * `NotificationPanel` — drop-down list rendered by `NotificationBell`.
 *
 * Renders unread notifications first (bold + blue tint) followed by
 * read ones, both ordered by `created_at` desc. Each row links to its
 * ticket; "Mark all read" calls `PATCH /notifications/read-all` while
 * optimistically clearing the badge through the Zustand store.
 */

"use client";

import { useRouter } from "next/navigation";
import { Check, CheckCheck, Bell, Trash2 } from "lucide-react";
import useNotificationStore from "@/stores/notificationStore";
import { useNotifications } from "@/hooks/useNotifications";
import { timeAgo } from "@/lib/utils";

const TYPE_ICONS: Record<string, string> = {
  assigned: "👤",
  commented: "💬",
  status_changed: "🔄",
  ticket_updated: "📝",
  ticket_deleted: "🗑️",
  deletion_requested: "📨",
  rag_indexed: "📚",
};

interface NotificationPanelProps {
  onClose: () => void;
}

export function NotificationPanel({ onClose }: NotificationPanelProps) {
  const router = useRouter();
  const notifications = useNotificationStore((s) => s.notifications);
  const { handleMarkAsRead, handleMarkAllAsRead, handleDeleteNotification } = useNotifications();

  const handleItemClick = async (id: string, ticketId: string) => {
    // Why: `ticket_deleted` notifications have no related ticket;
    // guard against routing to `/tickets/undefined`.
    if (!ticketId) return;
    await handleMarkAsRead(id);
    onClose();
    router.push(`/tickets/${ticketId}`);
  };

  const handleDeleteClick = async (
    e: React.MouseEvent<HTMLButtonElement>,
    notificationId: string,
  ) => {
    e.stopPropagation();
    await handleDeleteNotification(notificationId);
  };

  // Why: a per-item "mark as read" button is the only way to clear an
  // unread notification whose ticket has been deleted, because the
  // navigation path early-returns when `ticket_id` is missing.
  const handleMarkReadClick = async (
    e: React.MouseEvent<HTMLButtonElement>,
    notificationId: string,
  ) => {
    e.stopPropagation();
    await handleMarkAsRead(notificationId);
  };

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl shadow-lg border border-slate-200 z-50 overflow-hidden"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <span className="text-sm font-semibold text-slate-800">Notifications</span>
        {notifications.some((n) => !n.read) && (
          <button
            onClick={handleMarkAllAsRead}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
          >
            <CheckCheck className="w-3.5 h-3.5" />
            Mark all read
          </button>
        )}
      </div>

      <div className="max-h-80 overflow-y-auto">
        {notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-3">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
              <Bell className="w-6 h-6 text-slate-300" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-500">You&apos;re all caught up!</p>
              <p className="text-xs text-slate-400 mt-0.5">No new notifications right now</p>
            </div>
          </div>
        ) : (
          notifications.map((n) => (
            <div
              key={n.id}
              className={`w-full px-4 py-3 flex items-start gap-3 hover:bg-slate-50 transition-colors border-b border-slate-50 last:border-0 ${
                !n.read ? "bg-blue-50/50" : ""
              }`}
            >
              <button
                onClick={() => handleItemClick(n.id, n.ticket_id ?? "")}
                className="flex items-start gap-3 flex-1 min-w-0 text-left"
              >
                <span className="text-lg leading-none mt-0.5" aria-hidden>
                  {TYPE_ICONS[n.type] ?? "🔔"}
                </span>

                <div className="flex-1 min-w-0">
                  <p className={`text-sm leading-snug ${!n.read ? "font-medium text-slate-800" : "text-slate-600"}`}>
                    {n.message}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">{timeAgo(n.created_at)}</p>
                </div>

                {!n.read && (
                  <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 mt-1.5" aria-label="Unread" />
                )}
              </button>

              {!n.read && (
                <button
                  onClick={(e) => handleMarkReadClick(e, n.id)}
                  className="shrink-0 p-1.5 rounded-md text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                  aria-label="Mark as read"
                  title="Mark as read"
                >
                  <Check className="w-3.5 h-3.5" />
                </button>
              )}

              <button
                onClick={(e) => handleDeleteClick(e, n.id)}
                className="shrink-0 p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                aria-label="Delete notification"
                title="Delete notification"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
