/**
 * Notification store (Zustand).
 *
 * Owns the in-memory notification list plus the unread badge count.
 * Notifications enter the store from two sources:
 *
 *  1. **Initial fetch** — `GET /notifications` on first WebSocket
 *     connect, hydrated via `setNotifications`.
 *  2. **Real-time push** — WebSocket events handled by `useWebSocket`,
 *     which call `addNotification` / `syncRemoveNotification` /
 *     `syncMarkOneRead` / `syncMarkAllAsRead`.
 *
 * Whenever the server sends an authoritative `unread_count` we trust
 * it over the client-side derivation; otherwise the count is
 * recomputed from the list to avoid drift.
 *
 * The `refreshSignal` / `lastTicketId` / `deletedTicketId` fields are
 * a lightweight pub-sub used by `useTickets` to know when to re-fetch
 * after a WebSocket event without coupling the two stores directly.
 */

import { create } from "zustand";
import { Notification } from "@/types";
import api from "@/lib/api";

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  refreshSignal: number;
  lastTicketId: string | null;
  deletedTicketId: string | null;
  addNotification: (notification: Notification, serverUnreadCount?: number) => void;
  removeNotification: (id: string, serverUnreadCount?: number) => Promise<void>;
  syncRemoveNotification: (id: string, serverUnreadCount?: number) => void;
  syncUnreadCount: (count: number) => void;
  syncMarkAllAsRead: (serverUnreadCount?: number) => void;
  syncMarkOneRead: (id: string, serverUnreadCount?: number) => void;
  triggerRefresh: (ticketId?: string) => void;
  triggerDelete: (ticketId: string) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  setNotifications: (notifications: Notification[]) => void;
}

const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,
  refreshSignal: 0,
  lastTicketId: null,
  deletedTicketId: null,

  triggerRefresh: (ticketId) =>
    set((state) => ({
      refreshSignal: state.refreshSignal + 1,
      lastTicketId: ticketId || null,
      deletedTicketId: null
    })),

  triggerDelete: (ticketId) =>
    set((state) => ({
      // Why: bump the signal only when an id is supplied; consumers
      // (`useTickets`) already react to `deletedTicketId` alone.
      refreshSignal: ticketId ? state.refreshSignal + 1 : state.refreshSignal,
      deletedTicketId: ticketId || null,
      lastTicketId: null
    })),

  // Why: prefer the server's authoritative unread_count whenever it is
  // pushed; client-side derivation is the fallback.
  syncUnreadCount: (count) => set({ unreadCount: count }),

  syncMarkAllAsRead: (serverUnreadCount) =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: typeof serverUnreadCount === "number" ? serverUnreadCount : 0,
    })),

  syncMarkOneRead: (id, serverUnreadCount) =>
    set((state) => {
      const updated = state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      );
      return {
        notifications: updated,
        unreadCount: typeof serverUnreadCount === "number"
          ? serverUnreadCount
          : updated.filter((n) => !n.read).length,
      };
    }),

  setNotifications: (notifications) => {
    // Why: server pages can occasionally re-send a notification; dedupe
    // by id with a Map so the bell badge does not double-count.
    const uniqueMap = new Map();
    notifications.forEach((n) => uniqueMap.set(n.id, n));
    const unique = Array.from(uniqueMap.values());

    set({
      notifications: unique,
      unreadCount: unique.filter((n) => !n.read).length,
    });
  },

  addNotification: (notification, serverUnreadCount) => {
    set((state) => {
      if (state.notifications.some((n) => n.id === notification.id)) {
        // Why: duplicate WebSocket push — keep the list intact but
        // still honour the server's count if provided.
        if (typeof serverUnreadCount === "number") {
          return { ...state, unreadCount: serverUnreadCount };
        }
        return state;
      }
      const updated = [notification, ...state.notifications];
      return {
        notifications: updated,
        unreadCount: typeof serverUnreadCount === "number"
          ? serverUnreadCount
          : updated.filter((n) => !n.read).length,
      };
    });
  },

  removeNotification: async (id, serverUnreadCount) => {
    try {
      await api.delete(`/notifications/${id}`);
    } catch {
      // Why: optimistic removal — keep the local state consistent
      // across tabs even if the DELETE failed.
    }
    set((state) => {
      const updated = state.notifications.filter((n) => n.id !== id);
      return {
        notifications: updated,
        unreadCount: typeof serverUnreadCount === "number"
          ? serverUnreadCount
          : updated.filter((n) => !n.read).length,
      };
    });
  },

  syncRemoveNotification: (id, serverUnreadCount) => {
    set((state) => {
      const updated = state.notifications.filter((n) => n.id !== id);
      return {
        notifications: updated,
        unreadCount: typeof serverUnreadCount === "number"
          ? serverUnreadCount
          : updated.filter((n) => !n.read).length,
      };
    });
  },

  markAsRead: async (id) => {
    try {
      await api.patch(`/notifications/${id}/read`);
    } catch {
      // Why: optimistic — UI keeps the read state even if the PATCH
      // failed, the next /notifications fetch will reconcile.
    }
    set((state) => {
      const updated = state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      );
      return {
        notifications: updated,
        unreadCount: updated.filter((n) => !n.read).length,
      };
    });
  },

  markAllAsRead: async () => {
    try {
      await api.patch("/notifications/read-all");
    } catch {
      // Why: optimistic, same rationale as `markAsRead`.
    }
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },
}));

export default useNotificationStore;
