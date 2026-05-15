/**
 * Shared TypeScript types for the D4-Ticket AI frontend.
 *
 * Mirrors the Pydantic schemas exposed by the FastAPI backend
 * (`backend/app/schemas/`). Keeping the contract in a single module
 * makes it explicit when the API surface changes and lets every
 * component import a canonical shape instead of redeclaring inline
 * types.
 */

// ─── User ────────────────────────────────────────────────────────────────────

/** Public-facing user profile returned by `/users/*` endpoints. */
export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  /** ISO-8601 timestamp returned by the backend. */
  created_at: string;
}

// ─── Ticket ──────────────────────────────────────────────────────────────────

/** Workflow states the kanban columns are derived from. */
export type TicketStatus = "open" | "in_progress" | "in_review" | "closed";

/** Urgency tiers used for sorting and badge colour in the UI. */
export type TicketPriority = "low" | "medium" | "high" | "critical";

/** Ticket aggregate as returned by `GET /tickets/{ref}`. */
export interface Ticket {
  id: string;
  ticket_number: number;
  title: string;
  description: string | null;
  status: TicketStatus;
  priority: TicketPriority;
  author_id: string;
  assignee_id: string | null;
  client_url: string | null;
  client_summary: string | null;
  created_at: string;
  updated_at: string;
  author: User | null;
  assignee: User | null;
}

/** Paginated response for `GET /tickets`. */
export interface TicketListResponse {
  items: Ticket[];
  total: number;
  page: number;
  size: number;
}

/** Request body for `POST /tickets`. */
export interface TicketCreate {
  title: string;
  description?: string;
  priority?: TicketPriority;
  assignee_id?: string | null;
  client_url?: string | null;
  client_summary?: string | null;
}

/** Request body for `PATCH /tickets/{ref}` (every field is optional). */
export interface TicketUpdate {
  title?: string;
  description?: string;
  status?: TicketStatus;
  priority?: TicketPriority;
  assignee_id?: string | null;
  client_url?: string | null;
  client_summary?: string | null;
}

// ─── Comment ─────────────────────────────────────────────────────────────────

/** Comment posted on a ticket, with its author eager-loaded by the API. */
export interface Comment {
  id: string;
  ticket_id: string;
  author_id: string;
  content: string;
  created_at: string;
  author: User | null;
}

// ─── Attachment ──────────────────────────────────────────────────────────────

/**
 * Attachment metadata. The binary itself is fetched through the
 * presigned `download_url`; `use_for_rag` decides whether the AI
 * pipeline indexes the file as knowledge.
 */
export interface Attachment {
  id: string;
  ticket_id: string;
  uploader_id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  created_at: string;
  download_url: string | null;
  use_for_rag?: boolean;
}

// ─── Notification ────────────────────────────────────────────────────────────

/** Reason a notification was emitted (drives the icon shown in the bell). */
export type NotificationType =
  | "assigned"
  | "commented"
  | "status_changed"
  | "ticket_updated"
  | "ticket_deleted"
  | "deletion_requested"
  | "rag_indexed";

/** In-app notification targeted at a specific user. */
export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  ticket_id: string | null;
  message: string;
  read: boolean;
  created_at: string;
}

// ─── AI Chat ─────────────────────────────────────────────────────────────────

/**
 * Message rendered in the AI copilot sidebar.
 *
 * `actions` captures the agent tool calls executed during the turn
 * (e.g. `"Changed ticket #1 status to closed"`) so the user has
 * an audit trail; `ai_run_id` ties the message back to the persisted
 * `AIRun` row used for feedback and metrics.
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: string[];
  created_at: string;
  ai_run_id?: string;
  feedback_helped?: boolean | null;
  feedback_submitted?: boolean;
}

// ─── Ticket History ──────────────────────────────────────────────────────────

/** Single audit-trail entry returned by `GET /tickets/{ref}/history`. */
export interface TicketHistory {
  id: string;
  ticket_id: string | null;
  actor: User | null;
  field: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

// ─── Filters ─────────────────────────────────────────────────────────────────

/** Query parameters accepted by `GET /tickets`. */
export interface TicketFilters {
  status?: TicketStatus;
  priority?: TicketPriority;
  assignee_id?: string;
  search?: string;
  page?: number;
  size?: number;
  sort_by?: string;
  order?: "asc" | "desc";
}

/** Live AI subsystem snapshot returned by `GET /ai/status`. */
export interface AIStatus {
  provider: string;
  model: string;
  fallback_available: boolean;
  fallback_model: string | null;
  last_error: string | null;
  last_error_at: string | null;
  action_count: number;
  chat_count: number;
  diagnoses_count: number;
  rag_queries_count: number;
  rag_hits_count: number;
  fallback_count: number;
  success_count: number;
  error_count: number;
  last_latency_ms: number | null;
  avg_latency_ms: number | null;
  last_surface: string | null;
  last_rag_source: string;
}

/** Global AI dashboard payload returned by `GET /ai/stats`. */
export interface AIStatsSummary {
  total_runs: number;
  runs_by_surface: Record<string, number>;
  success_rate: number;
  fallback_rate: number;
  total_rag_queries: number;
  rag_hit_rate: number;
  positive_feedback_count: number;
  negative_feedback_count: number;
  helped_rate: number;
  tickets_closed_with_ai: number;
  tickets_closed_without_ai: number;
  avg_time_to_close_with_ai_hours: number | null;
  avg_time_to_close_without_ai_hours: number | null;
  total_estimated_cost_usd: number;
  avg_cost_per_run_usd: number;
  avg_cost_per_ticket_with_ai_usd: number;
}

/** Per-ticket AI metrics returned by `GET /ai/stats/tickets/{ref}`. */
export interface AITicketStats {
  ticket_id: string;
  diagnosis_runs: number;
  chat_runs: number;
  rag_queries_count: number;
  rag_hit_rate: number;
  last_ai_used_at: string | null;
  positive_feedback_count: number;
  negative_feedback_count: number;
  helped: boolean | null;
  first_closed_at: string | null;
  time_to_close_hours: number | null;
  estimated_cost_usd: number;
}

/** Provider override the user can pick from the AI menu. */
export type AIPreference = "auto" | "openai" | "google";

/** Request body for `POST /tickets/{ref}/reply-draft`. */
export interface ReplyDraftRequest {
  resolution_note: string;
  preferred_provider?: AIPreference;
}

/** Response shape for `POST /tickets/{ref}/reply-draft`. */
export interface ReplyDraftResponse {
  draft: string;
  ai_run_id: string;
}
