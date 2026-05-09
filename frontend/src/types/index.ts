/**
 * Shared TypeScript types for the D4-Ticket AI frontend.
 *
 * These mirror the Pydantic schemas from the FastAPI backend.
 * Keeping them in one place makes it easy to update when the API changes.
 */

// ─── User ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  created_at: string; // ISO 8601 string from the API
}

// ─── Ticket ──────────────────────────────────────────────────────────────────

export type TicketStatus = "open" | "in_progress" | "in_review" | "closed";
export type TicketPriority = "low" | "medium" | "high" | "critical";

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

export interface TicketListResponse {
  items: Ticket[];
  total: number;
  page: number;
  size: number;
}

export interface TicketCreate {
  title: string;
  description?: string;
  priority?: TicketPriority;
  assignee_id?: string | null;
  client_url?: string | null;
  client_summary?: string | null;
}

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

export interface Comment {
  id: string;
  ticket_id: string;
  author_id: string;
  content: string;
  created_at: string;
  author: User | null;
}

// ─── Attachment ──────────────────────────────────────────────────────────────

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

export type NotificationType =
  | "assigned"
  | "commented"
  | "status_changed"
  | "ticket_updated"
  | "ticket_deleted"
  | "deletion_requested";

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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: string[]; // Actions the AI performed (e.g., "Changed ticket #1 status to closed")
  created_at: string;
  ai_run_id?: string;
  feedback_helped?: boolean | null;
  feedback_submitted?: boolean;
}

// ─── Ticket History ──────────────────────────────────────────────────────────

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

export type AIPreference = "auto" | "openai" | "google";
