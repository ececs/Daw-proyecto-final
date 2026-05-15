/**
 * `useTickets` — paginated ticket list with optimistic mutations.
 *
 * Responsibilities:
 *
 * - Fetch `GET /tickets` with the active filters and expose
 *   `tickets`, `total`, `isLoading`, `error`.
 * - Apply optimistic UI for status drags and deletes, rolling back
 *   on API failure so the user sees an immediate response without
 *   losing consistency.
 * - React to the `notificationStore` refresh signal so WebSocket
 *   events from other users (or other tabs) keep the list in sync
 *   without polling.
 *
 * **Design note** — A plain `useState` + `useEffect` is used instead
 * of React Query / SWR because the scope is small and the team
 * wanted minimum dependencies. Caching and background refetch are
 * implemented inline.
 */

"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import api from "@/lib/api";
import { integrateCreatedTicket } from "@/lib/ticketRealtime";
import useNotificationStore from "@/stores/notificationStore";
import { useToast } from "./use-toast";
import { Ticket, TicketFilters, TicketListResponse, TicketStatus, TicketUpdate } from "@/types";

interface UseTicketsReturn {
  tickets: Ticket[];
  total: number;
  isLoading: boolean;
  error: string | null;
  /** Force a full network re-fetch with the current filters. */
  refetch: () => void;
  /** Merge a ticket created in this client into the local list. */
  insertTicket: (ticket: Ticket) => void;
  /** Optimistic status update with automatic rollback on failure. */
  updateTicketStatus: (ticketId: string, newStatus: TicketStatus) => Promise<void>;
  /** Patch arbitrary ticket fields and refresh the local row. */
  updateTicket: (ticketId: string, data: TicketUpdate) => Promise<Ticket>;
  /** Optimistic delete with automatic rollback on failure. */
  deleteTicket: (ticketId: string) => Promise<void>;
}

export function useTickets(filters: TicketFilters = {}): UseTicketsReturn {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Why: `fetchKey` is a manual cache-busting nonce; incrementing it
  // re-runs the fetch effect without touching the filters.
  const [fetchKey, setFetchKey] = useState(0);
  const { toast } = useToast();

  const refetch = useCallback(() => setFetchKey((k) => k + 1), []);

  /**
   * Merge a ticket created in this client (form modal) into the
   * cached list without re-fetching. The WebSocket `ticket_created`
   * fired by the same POST is a no-op because
   * `integrateCreatedTicket` deduplicates by id.
   */
  const insertTicket = useCallback((ticket: Ticket) => {
    setTickets((prev) => {
      if (prev.some((t) => t.id === ticket.id)) {
        return prev.map((t) => (t.id === ticket.id ? ticket : t));
      }
      const merged = integrateCreatedTicket(prev, ticket, filters);
      if (merged.needsRefetch) {
        refetch();
        return prev;
      }
      if (merged.totalDelta !== 0) {
        setTotal((n) => n + merged.totalDelta);
      }
      return merged.tickets;
    });
  }, [filters, refetch]);

  const refreshSignal = useNotificationStore((s) => s.refreshSignal);
  const lastTicketId = useNotificationStore((s) => s.lastTicketId);
  const deletedTicketId = useNotificationStore((s) => s.deletedTicketId);
  const lastHandledSignal = useRef(0);

  // React to refresh signals from the notification store (driven by
  // WebSocket events). Branches:
  //  1. Deletion fast path — drop the row locally if still present.
  //  2. Single-ticket update — fetch only the changed row and merge.
  //  3. Fallback — full network refetch.
  useEffect(() => {
    if (refreshSignal === 0) return;
    // Why: ignore re-runs caused by clearing `deletedTicketId` after
    // the fast path; without this guard we would issue a redundant
    // full refetch.
    if (refreshSignal === lastHandledSignal.current) return;
    lastHandledSignal.current = refreshSignal;

    if (deletedTicketId) {
      // Why: covers deletions originated in other sessions. The local
      // optimistic delete already removed the row in this session, so
      // this branch is a safety net.
      setTickets((prev) => {
        const existed = prev.some((t) => t.id === deletedTicketId);
        if (existed) setTotal((n) => Math.max(0, n - 1));
        return prev.filter((t) => t.id !== deletedTicketId);
      });
      // Why: clear `deletedTicketId` after consuming it so the next
      // signal does not look like a ghost deletion. The `lastHandledSignal`
      // guard above prevents the resulting re-run from refetching.
      setTimeout(() => useNotificationStore.getState().triggerDelete(""), 0);
    } else if (lastTicketId && lastTicketId !== "None" && lastTicketId !== "undefined" && lastTicketId !== "*") {
      // Why: targeted refresh — pull just the affected ticket and let
      // `integrateCreatedTicket` decide whether the local merge is
      // sufficient or a full refetch is needed.
      api.get<Ticket>(`/tickets/${lastTicketId}`)
        .then(({ data }) => {
          setTickets((prev) => {
            const exists = prev.some((t) => t.id === data.id);
            if (!exists) {
              const merged = integrateCreatedTicket(prev, data, filters);
              if (merged.needsRefetch) {
                refetch();
                return prev;
              }
              if (merged.totalDelta !== 0) {
                setTotal((n) => n + merged.totalDelta);
              }
              return merged.tickets;
            }
            return prev.map((t) => (t.id === data.id ? data : t));
          });
        })
        .catch((err) => {
          console.error("Failed to fetch partial update, falling back to full refetch", err);
          refetch();
        });
    } else {
      refetch();
    }
  }, [refreshSignal, lastTicketId, deletedTicketId, filters, refetch]);

  // Why: depend on the primitive values, not the `filters` object
  // reference, so parent re-renders that produce a new object
  // identity but the same values do not trigger a network re-fetch.
  const filtersKey = useMemo(
    () => JSON.stringify({
      status: filters.status,
      priority: filters.priority,
      assignee_id: filters.assignee_id,
      search: filters.search,
      page: filters.page,
      size: filters.size,
      sort_by: filters.sort_by,
      order: filters.order,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filters.status, filters.priority, filters.assignee_id, filters.search, filters.page, filters.size, filters.sort_by, filters.order]
  );

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    // Why: drop `undefined` / `null` / `""` from the query string so
    // the backend does not have to filter them out.
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== "")
    );

    api.get<TicketListResponse>("/tickets", { params })
      .then(({ data }) => {
        if (!cancelled) {
          setTickets(data.items);
          setTotal(data.total);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.response?.data?.detail ?? "Failed to load tickets");
          setIsLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [fetchKey, filtersKey]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Optimistically update a ticket's status, then PATCH the API.
   * Restores the previous status and shows a destructive toast on
   * failure.
   */
  const updateTicketStatus = useCallback(async (ticketId: string, newStatus: TicketStatus) => {
    const previous = tickets.find((t) => t.id === ticketId);
    setTickets((prev) =>
      prev.map((t) => (t.id === ticketId ? { ...t, status: newStatus } : t))
    );

    try {
      await api.patch(`/tickets/${ticketId}`, { status: newStatus });
    } catch {
      if (previous) {
        setTickets((prev) =>
          prev.map((t) => (t.id === ticketId ? { ...t, status: previous.status } : t))
        );
      }
      toast({
        variant: "destructive",
        title: "Connection Error",
        description: "Failed to update ticket status. Changes have been rolled back.",
      });
    }
  }, [tickets, toast]);

  /** Patch arbitrary ticket fields and refresh the matching row in place. */
  const updateTicket = useCallback(async (ticketId: string, data: TicketUpdate): Promise<Ticket> => {
    const { data: updated } = await api.patch<Ticket>(`/tickets/${ticketId}`, data);
    setTickets((prev) =>
      prev.map((t) => (t.id === ticketId ? updated : t))
    );
    return updated;
  }, []);

  /**
   * Optimistic delete with rollback. Re-throws on 403 so the caller
   * can decide whether to surface "not the author" through a
   * tailored UI flow instead of the generic destructive toast.
   */
  const deleteTicket = useCallback(async (ticketId: string) => {
    const snapshot = tickets;
    setTickets((prev) => prev.filter((t) => t.id !== ticketId));
    setTotal((n) => n - 1);

    try {
      await api.delete(`/tickets/${ticketId}`);
    } catch (err) {
      setTickets(snapshot);
      setTotal((n) => n + 1);
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        throw err;
      }
      toast({
        variant: "destructive",
        title: "Deletion Failed",
        description: "Could not delete ticket. Please check your connection and try again.",
      });
      throw err;
    }
  }, [tickets, toast]);

  return { tickets, total, isLoading, error, refetch, insertTicket, updateTicketStatus, updateTicket, deleteTicket };
}
