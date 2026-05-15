/**
 * `useNotifications` — hydrate the notification store on mount.
 *
 * Fetches `GET /notifications` once and feeds the result into the
 * Zustand store. The store actions already handle the per-item PATCH
 * / DELETE calls and the optimistic UI updates, so this hook only
 * re-exports them with friendlier names for the consuming components.
 *
 * Real-time updates arrive through `useWebSocket`, which writes
 * directly into the same store.
 */

"use client";

import { useEffect } from "react";
import api from "@/lib/api";
import useNotificationStore from "@/stores/notificationStore";
import { Notification } from "@/types";

export function useNotifications() {
  const { setNotifications, markAsRead, markAllAsRead, removeNotification } = useNotificationStore();

  useEffect(() => {
    api.get<Notification[]>("/notifications").then(({ data }) => {
      setNotifications(data);
    });
  }, [setNotifications]);

  return {
    handleMarkAsRead: markAsRead,
    handleMarkAllAsRead: markAllAsRead,
    handleDeleteNotification: removeNotification,
  };
}
