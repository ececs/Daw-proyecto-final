/**
 * `useWebSocket` — single duplex connection driving the real-time UI.
 *
 * Connects to the FastAPI WebSocket endpoint (`/ws?token=<jwt>`) and
 * fans incoming messages out to the Zustand notification store and
 * the toast system.
 *
 * Connection lifecycle:
 *
 *  1. On mount, the JWT is consumed from props and a `WebSocket` is
 *     opened.
 *  2. If the socket closes with a non-1000 code (e.g. network drop)
 *     a 2-second reconnect is scheduled automatically.
 *  3. On unmount the socket is closed cleanly with code 1000 so the
 *     reconnect timer is *not* armed.
 *
 * **Why the token travels in the query string**: native browser
 * WebSockets cannot carry custom headers. The backend cookie is
 * `HttpOnly` and unreadable by JavaScript, so the token is forwarded
 * from the server layout as a prop.
 */

"use client";

import { useEffect, useRef } from "react";
import useNotificationStore from "@/stores/notificationStore";
import { Notification } from "@/types";
import { useToast } from "@/hooks/use-toast";

const WS_URL = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") ?? "ws://localhost:8000";
const IS_DEV = process.env.NODE_ENV !== "production";

export function useWebSocket(token: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);
    const {
      addNotification,
      syncRemoveNotification,
      syncMarkOneRead,
      triggerRefresh,
      triggerDelete,
      syncUnreadCount,
      syncMarkAllAsRead,
    } = useNotificationStore();
  const { toast } = useToast();

  useEffect(() => {
    if (!token) return;

    const connect = () => {
      // Why: clear any in-flight socket *before* opening a new one;
      // nulling `onclose` first prevents the cleanup from triggering
      // the auto-reconnect path.
      if (ws.current) {
        ws.current.onclose = null;
        ws.current.close();
      }

      // Why: defend against `NEXT_PUBLIC_API_URL` configured with a
      // trailing slash, which would produce `//ws` and 404 on some
      // hosting proxies.
      const baseUrl = WS_URL.endsWith("/") ? WS_URL.slice(0, -1) : WS_URL;
      const socket = new WebSocket(`${baseUrl}/ws?token=${token}`);
      ws.current = socket;

      socket.onmessage = (event) => {
        try {
          const wsMsg = JSON.parse(event.data);
          const { type, data, ticket_id, message } = wsMsg;
          if (IS_DEV && type !== "ping") {
            console.debug("🔌 WS Message:", { type, ticket_id, data });
          }

          if (type === "ping") return;

          switch (type) {
            case "ticket_deleted":
            case "TICKET_DELETED": // Backwards compatibility with the legacy uppercase type
              if (data && data.id) {
                triggerDelete(String(data.id));
              }
              break;

            case "ticket_created":
              if (data && data.ticket_number != null) {
                triggerRefresh(String(data.ticket_number));
              } else if (data && data.id) {
                triggerRefresh(String(data.id));
              } else {
                triggerRefresh("*");
              }
              break;

            case "web_scrape_completed":
              if (ticket_id) {
                triggerRefresh(String(ticket_id));
                toast({
                  title: "Web analysis finished",
                  description: message || "The AI has finished analyzing the client URL.",
                  variant: "success",
                });
              }
              break;

            case "notification":
              if (data && data.id) {
                // Why: trust the server's `unread_count` when present
                // so the badge stays accurate even on duplicate pushes.
                addNotification(
                  data as unknown as Notification,
                  typeof data.unread_count === "number" ? data.unread_count : undefined,
                );
                if (data.ticket_id) triggerRefresh(String(data.ticket_id));

                toast({
                  title: "New notification",
                  description: data.message || "You have a new update.",
                });
              }
              break;

            case "notification_read":
              if (data && data.id) {
                syncMarkOneRead(
                  String(data.id),
                  typeof data.unread_count === "number" ? data.unread_count : undefined,
                );
              }
              break;

            case "notification_deleted":
              if (data && data.id) {
                syncRemoveNotification(
                  String(data.id),
                  typeof data.unread_count === "number" ? data.unread_count : undefined,
                );
              }
              break;

            case "notifications_read_all":
              syncMarkAllAsRead(
                data && typeof data.unread_count === "number" ? data.unread_count : 0,
              );
              break;

            case "ticket_updated":
              if (data && data.ticket_number != null) {
                triggerRefresh(String(data.ticket_number));
              } else if (ticket_id) {
                triggerRefresh(String(ticket_id));
              } else if (data && data.id) {
                triggerRefresh(String(data.id));
              } else {
                triggerRefresh("*");
              }
              break;

            case "system_alert":
              // Why: sync the badge from the server-authoritative
              // unread count piggybacked on the handshake.
              if (data && typeof data.unread_count === "number") {
                syncUnreadCount(data.unread_count);
              }
              // Why: filter the handshake message so it does not
              // produce an empty "System notice" toast on every
              // (re)connect. The literal must stay in sync with the
              // backend (`backend/app/api/v1/ws.py`).
              if (message && message !== "Initial state loaded") {
                toast({
                  title: "System notice",
                  description: message,
                  variant: message.toLowerCase().includes("error") ? "destructive" : "default",
                });
              }
              break;

            default:
              if (IS_DEV) {
                console.warn("Unknown WebSocket message type:", type);
              }
          }
        } catch (err) {
          if (IS_DEV) {
            console.error("Failed to parse WebSocket message:", err);
          }
        }
      };

      socket.onclose = (event) => {
        if (IS_DEV) {
          console.log(`WebSocket closed: ${event.code} ${event.reason}`);
        }
        // Why: 1000 means a clean close (component unmount); anything
        // else is treated as an unexpected drop that triggers a retry.
        if (event.code !== 1000) {
          reconnectTimeout.current = setTimeout(connect, 2000);
        }
      };

      socket.onerror = () => {
        socket.close(); // `onclose` will schedule the reconnect.
      };
    };

    connect();

    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      if (ws.current) {
        // Why: detach `onclose` first so the close below does not
        // re-arm the reconnect timer during component teardown.
        ws.current.onclose = null;
        ws.current.close(1000, "Component unmounted");
      }
    };
  }, [token, addNotification]); // eslint-disable-line react-hooks/exhaustive-deps
}
