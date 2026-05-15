/**
 * Pure helpers used by `useTickets` to react to real-time
 * `ticket_created` WebSocket events without re-fetching the whole
 * page when avoidable.
 *
 * The reasoning lives here instead of in the hook so it can be unit
 * tested in isolation (see `ticketRealtime.test.ts`).
 */

import { Ticket, TicketFilters, TicketPriority, TicketStatus } from "@/types";

const PRIORITY_ORDER: Record<TicketPriority, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
};

const STATUS_ORDER: Record<TicketStatus, number> = {
  open: 0,
  in_progress: 1,
  in_review: 2,
  closed: 3,
};

type SortField = "title" | "status" | "priority" | "created_at";
type SortDir = "asc" | "desc";

/**
 * Outcome of integrating a new ticket into the cached list:
 *
 * - `tickets`     — the (possibly mutated) ticket array to render.
 * - `totalDelta`  — increment to apply to the total counter (0 or 1).
 * - `needsRefetch`— `true` when the local merge cannot guarantee
 *                   correctness (search active, beyond first page),
 *                   so the caller must trigger a network re-fetch.
 */
export interface TicketInsertResult {
  tickets: Ticket[];
  totalDelta: number;
  needsRefetch: boolean;
}

/** Check whether the ticket would survive the non-search filters. */
function matchesNonSearchFilters(ticket: Ticket, filters: TicketFilters): boolean {
  if (filters.status && ticket.status !== filters.status) return false;
  if (filters.priority && ticket.priority !== filters.priority) return false;
  if (filters.assignee_id && ticket.assignee_id !== filters.assignee_id) return false;
  return true;
}

/** Comparator matching the backend's `sort_by` / `order` semantics. */
function compareTickets(a: Ticket, b: Ticket, sortBy: SortField, order: SortDir): number {
  let base = 0;

  switch (sortBy) {
    case "title":
      base = a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
      break;
    case "status":
      base = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
      break;
    case "priority":
      base = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
      break;
    case "created_at":
    default:
      base = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      break;
  }

  return order === "asc" ? base : -base;
}

/**
 * Decide how to integrate a newly-created ticket into the cached list.
 *
 * Returns a fresh list and tells the caller whether the data is still
 * authoritative or whether a network re-fetch is required (search
 * filters or pages beyond the first cannot be merged locally because
 * we lack the rest of the dataset).
 *
 * @param prev    Current cached ticket list.
 * @param created Ticket pushed by the backend over WebSocket.
 * @param filters Active filters (page / size / sort / search).
 */
export function integrateCreatedTicket(
  prev: Ticket[],
  created: Ticket,
  filters: TicketFilters,
): TicketInsertResult {
  if (prev.some((ticket) => ticket.id === created.id)) {
    // Why: a `ticket_created` for an id we already have means the
    // server is reconciling — refresh the row in place.
    return {
      tickets: prev.map((ticket) => (ticket.id === created.id ? created : ticket)),
      totalDelta: 0,
      needsRefetch: false,
    };
  }

  if (filters.search) {
    // Why: search results are scored on the backend; we cannot decide
    // locally whether a brand-new ticket should appear or where.
    return { tickets: prev, totalDelta: 0, needsRefetch: true };
  }

  if (!matchesNonSearchFilters(created, filters)) {
    return { tickets: prev, totalDelta: 0, needsRefetch: false };
  }

  const page = filters.page ?? 1;
  if (page > 1) {
    // Why: pages beyond the first reflect a slice of the global list
    // we do not hold in memory; only the server can produce the right
    // page after the insertion.
    return { tickets: prev, totalDelta: 0, needsRefetch: true };
  }

  const sortBy = (filters.sort_by as SortField | undefined) ?? "created_at";
  const order = filters.order ?? "desc";
  const next = [...prev, created].sort((a, b) => compareTickets(a, b, sortBy, order));
  const size = filters.size;
  const limited = typeof size === "number" && size > 0 ? next.slice(0, size) : next;

  return {
    tickets: limited,
    totalDelta: 1,
    needsRefetch: false,
  };
}
