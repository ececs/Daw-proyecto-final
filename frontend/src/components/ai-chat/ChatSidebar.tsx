/**
 * `ChatSidebar` — floating AI assistant panel docked to the right
 * of the dashboard.
 *
 * **Conversation state** lives in local `useState` (not Zustand): it
 * is session-scoped and not shared across components, so introducing
 * a global store would be unjustified ceremony.
 *
 * **Transport** — each user message is `POST`ed to `/ai/chat` and
 * the response is consumed as an SSE stream via the native
 * `fetch()` + `ReadableStream` API. `EventSource` cannot carry a
 * request body, so a text-decoder loop is used instead. Tokens are
 * appended to the trailing assistant message in real time and
 * `tool_call` events get pushed into the message's `actions` array.
 *
 * **Special events:** the backend emits
 * `__DELETE_REQUESTED__:<id>:<title>` (and `__DELETE_REQUEST_OFFER__`)
 * sentinels that the SSE router converts into UI confirmation
 * dialogs — see the corresponding queue state below.
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Bot, Loader2, Wrench, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import { useParams } from "next/navigation";
import { useSelectionStore } from "@/stores/useSelectionStore";
import { ChatMessage } from "@/types";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import api from "@/lib/api";
import { getAIPreference } from "@/lib/aiPreference";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ChatSidebarProps {
  onClose: () => void;
}

export function ChatSidebar({ onClose }: ChatSidebarProps) {
  type PendingDelete = { ticket_id: string; ticket_title: string };
  type PendingDeleteRequest = { ticket_id: string; ticket_title: string };
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm your AI assistant. I can help you manage tickets — create, search, update status, add comments, and reassign. What would you like to do?",
      created_at: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isRequestingDelete, setIsRequestingDelete] = useState(false);
  const [deleteQueue, setDeleteQueue] = useState<PendingDelete[]>([]);
  const [deleteRequestQueue, setDeleteRequestQueue] = useState<PendingDeleteRequest[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Why: the thread id is persisted so the LangGraph checkpointer on
  // the backend can rehydrate the conversation across reloads.
  const threadIdRef = useRef<string>("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("ai_thread_id");
      if (stored) {
        threadIdRef.current = stored;
      } else {
        const newId = crypto.randomUUID();
        threadIdRef.current = newId;
        localStorage.setItem("ai_thread_id", newId);
      }
    }
  }, []);

  const resetChat = useCallback(() => {
    const newId = crypto.randomUUID();
    threadIdRef.current = newId;
    if (typeof window !== "undefined") {
      localStorage.setItem("ai_thread_id", newId);
    }
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: "Session reset. How can I help you today?",
        created_at: new Date().toISOString(),
      },
    ]);
  }, []);

  const params = useParams();
  const currentTicketId = params?.id as string | undefined;
  const { selectedTicketIds } = useSelectionStore();
  const pendingDelete = deleteQueue[0] ?? null;
  const pendingDeleteRequest = deleteRequestQueue[0] ?? null;

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput("");
    setIsStreaming(true);

    // Append user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };

    // Placeholder for the assistant's streaming response
    const assistantId = crypto.randomUUID();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      actions: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    // With persistent memory: send only the new user message + thread_id.
    // The agent recovers full conversation history from its PostgreSQL checkpoint.
    // Fallback (no checkpointer): send all messages as before.
    const historyToSend = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      abortRef.current = new AbortController();

      const cookieMatch = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
      const authHeader = cookieMatch
        ? `Bearer ${decodeURIComponent(cookieMatch[1])}`
        : "";

      const response = await fetch(`${API_URL}/api/v1/ai/chat`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(authHeader ? { Authorization: authHeader } : {}),
        },
        body: JSON.stringify({
          messages: historyToSend,
          thread_id: threadIdRef.current,
          current_ticket_id: currentTicketId,
          selected_ticket_ids: selectedTicketIds,
          preferred_provider: getAIPreference(),
        }),
        signal: abortRef.current.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`API error: ${response.status}`);
      }

      // Parse the SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // Labeled outer loop so the "done" event can exit both the for and the while.
      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? ""; // Keep any incomplete event in the buffer

        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;

          try {
            const event = JSON.parse(line) as {
              type: string;
              content?: string;
              name?: string;
              result?: string;
              thread_id?: string;
              ai_run_id?: string;
              ticket_id?: string;
              ticket_title?: string;
            };

            if (event.type === "session") {
              if (event.thread_id) {
                threadIdRef.current = event.thread_id as string;
                localStorage.setItem("ai_thread_id", event.thread_id as string);
              }
              if (event.ai_run_id) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, ai_run_id: event.ai_run_id, feedback_submitted: false, feedback_helped: null }
                      : m
                  )
                );
              }
            } else if (event.type === "token" && event.content) {
              // Append text token to the assistant message
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: m.content + event.content }
                    : m
                )
              );
            } else if (event.type === "error" && event.content) {
              // Show configuration/server error in the chat
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: event.content || "Server error." }
                    : m
                )
              );
            } else if (event.type === "tool_call" && event.name) {
              // Append executed action to the actions list
              const actionLabel = formatToolAction(event.name, event.result ?? "");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, actions: [...(m.actions ?? []), actionLabel] }
                    : m
                )
              );
            } else if (event.type === "confirmation_required" && event.ticket_id) {
              // Queue delete confirmations so multiple selected tickets are confirmed one by one.
              const ticketId = event.ticket_id;
              const ticketTitle = event.ticket_title ?? "this ticket";
              setDeleteQueue((prev) => [
                ...prev,
                {
                  ticket_id: ticketId,
                  ticket_title: ticketTitle,
                },
              ]);
            } else if (event.type === "deletion_request_offer" && event.ticket_id) {
              const ticketId = event.ticket_id;
              const ticketTitle = event.ticket_title ?? "this ticket";
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content: `You cannot delete "${ticketTitle}" because only the author can delete it. Would you like me to notify the author for you?`,
                  created_at: new Date().toISOString(),
                },
              ]);
              setDeleteRequestQueue((prev) => [
                ...prev,
                {
                  ticket_id: ticketId,
                  ticket_title: ticketTitle,
                },
              ]);
            } else if (event.type === "done") {
              break outer;
            }
          } catch {
            // Ignore malformed SSE events
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return; // User dismissed the request

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
              ? {
                ...m,
                content: `Error: could not connect to the AI (${err instanceof Error ? err.message : "Something went wrong"}).`,
              }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
    }
  }, [input, isStreaming, messages, selectedTicketIds, currentTicketId]);

  /**
   * Executed when the user confirms deletion from the ConfirmDialog.
   * Calls the REST DELETE endpoint directly — the AI never touches this path.
   */
  const handleConfirmDelete = async () => {
    if (!pendingDelete || isDeleting) return;
    const { ticket_id, ticket_title } = pendingDelete;
    setIsDeleting(true);
    try {
      await api.delete(`/tickets/${ticket_id}`);
      setDeleteQueue((prev) => prev.slice(1));
      // Add a system message confirming the deletion
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `✅ Ticket "${ticket_title}" has been permanently deleted.`,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Please try again.";
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setDeleteQueue((prev) => prev.slice(1));
        setDeleteRequestQueue((prev) => [
          ...prev,
          {
            ticket_id,
            ticket_title,
          },
        ]);
      }
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `❌ Could not delete ticket "${ticket_title}". ${detail}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancelDelete = () => {
    if (isDeleting) return;
    setDeleteQueue((prev) => prev.slice(1));
  };

  const handleConfirmDeleteRequest = async () => {
    if (!pendingDeleteRequest || isRequestingDelete) return;
    const { ticket_id, ticket_title } = pendingDeleteRequest;
    setIsRequestingDelete(true);
    try {
      await api.post(`/tickets/${ticket_id}/deletion-request`);
      setDeleteRequestQueue((prev) => prev.slice(1));
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `📨 I notified the author and asked them to delete "${ticket_title}".`,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Please try again.";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `❌ Could not send a deletion request for "${ticket_title}". ${detail}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsRequestingDelete(false);
    }
  };

  const handleCancelDeleteRequest = () => {
    if (isRequestingDelete) return;
    setDeleteRequestQueue((prev) => prev.slice(1));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const submitFeedback = useCallback(async (messageId: string, aiRunId: string, helped: boolean) => {
    if (feedbackSubmittingId) return;
    setFeedbackSubmittingId(messageId);
    try {
      await api.post("/ai/feedback", {
        ai_run_id: aiRunId,
        helped,
        label: helped ? "helpful" : "not_helpful",
      });
      setMessages((prev) =>
        prev.map((message) =>
          message.id === messageId
            ? { ...message, feedback_submitted: true, feedback_helped: helped }
            : message
        )
      );
    } catch (error) {
      console.error("Failed to submit AI feedback", error);
    } finally {
      setFeedbackSubmittingId(null);
    }
  }, [feedbackSubmittingId]);

  return (
    <>
    <div className="fixed inset-x-3 bottom-28 top-4 z-[200] flex flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl animate-in slide-in-from-bottom-4 fade-in sm:inset-x-auto sm:top-auto sm:right-4 sm:bottom-4 sm:h-[560px] sm:w-[380px]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 rounded-t-2xl bg-gradient-to-r from-blue-600 to-blue-500">
        <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-white">AI Assistant</p>
          <p className="text-[10px] text-blue-200">
            Powered by LangGraph · {selectedTicketIds.length > 0 ? `${selectedTicketIds.length} tickets selected` : "memory enabled"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={resetChat}
            title="New Chat"
            aria-label="New conversation"
            className="p-1.5 text-blue-100 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            aria-label="Close chat"
            className="p-1.5 text-blue-100 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-2 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            {/* Avatar */}
            {msg.role === "assistant" && (
              <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-3.5 h-3.5 text-blue-600" />
              </div>
            )}

            <div className={`flex flex-col gap-1 max-w-[80%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
              {/* Bubble */}
              <div
                className={`rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-tr-sm"
                    : "bg-slate-100 text-slate-800 rounded-tl-sm"
                }`}
              >
                {msg.content || (
                  <span className="flex items-center gap-1.5 text-slate-400 animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Thinking...
                  </span>
                )}
              </div>

                {/* Tool actions (highlighted chips) */}
                {msg.actions && msg.actions.length > 0 && (
                  <div className="flex flex-col gap-1 w-full">
                    {msg.actions.map((action, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-1.5 bg-green-50 border border-green-100 rounded-lg px-2.5 py-1.5 text-xs text-green-700 animate-in fade-in slide-in-from-left-2 duration-300 min-w-0"
                        style={{ animationDelay: `${i * 120}ms`, animationFillMode: "backwards" }}
                      >
                        <Wrench className="w-3 h-3 shrink-0" />
                        <span className="truncate">{action}</span>
                      </div>
                    ))}
                  </div>
                )}

                {msg.role === "assistant" && msg.ai_run_id && (
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={() => submitFeedback(msg.id, msg.ai_run_id!, true)}
                      disabled={msg.feedback_submitted || feedbackSubmittingId === msg.id}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] transition-colors ${
                        msg.feedback_helped === true
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-slate-100 text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"
                      } disabled:opacity-70`}
                    >
                      {feedbackSubmittingId === msg.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3 h-3" />}
                      Ayudó
                    </button>
                    <button
                      onClick={() => submitFeedback(msg.id, msg.ai_run_id!, false)}
                      disabled={msg.feedback_submitted || feedbackSubmittingId === msg.id}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] transition-colors ${
                        msg.feedback_helped === false
                          ? "bg-rose-100 text-rose-700"
                          : "bg-slate-100 text-slate-600 hover:bg-rose-50 hover:text-rose-700"
                      } disabled:opacity-70`}
                    >
                      {feedbackSubmittingId === msg.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsDown className="w-3 h-3" />}
                      No ayudó
                    </button>
                  </div>
                )}
              </div>
            </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-slate-100 rounded-b-2xl">
        <div className="flex gap-2 items-end">
          <textarea
            aria-label="Mensaje para el asistente"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask me to manage your tickets..."
            rows={2}
            disabled={isStreaming}
            className="flex-1 resize-none border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder:text-slate-400"
          />
          <button
            onClick={sendMessage}
            disabled={isStreaming || !input.trim()}
            aria-label="Enviar mensaje"
            className="p-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors shrink-0"
            title="Send (Enter)"
          >
            {isStreaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        <p className="text-[10px] text-slate-400 mt-1.5 text-center">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>

      {/* Server-enforced delete confirmation — triggered by the AI, confirmed by the human */}
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete ticket"
        description={`Are you sure you want to permanently delete "${pendingDelete?.ticket_title}"? This action cannot be undone.`}
        confirmLabel="Delete ticket"
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
      <ConfirmDialog
        open={!pendingDelete && !!pendingDeleteRequest}
        title="Only the author can delete this ticket"
        description={`You do not have permission to delete "${pendingDeleteRequest?.ticket_title}". Do you want to notify the author and ask them to delete it?`}
        confirmLabel="Send request"
        onConfirm={handleConfirmDeleteRequest}
        onCancel={handleCancelDeleteRequest}
      />
    </>
  );
}

/**
 * Convert a tool name + result into a human-readable action label.
 * Shown as green chips below the assistant message.
 */
function formatToolAction(toolName: string, result: string): string {
  const labels: Record<string, string> = {
    query_tickets: "Searched tickets",
    get_ticket: "Fetched ticket details",
    create_ticket: "Created a ticket",
    change_status: "Updated ticket status",
    add_comment: "Added a comment",
    reassign_ticket: "Reassigned ticket",
    update_ticket: "Updated ticket",
    delete_ticket: "Deletion requested",
    search_knowledge: "Searched knowledge base",
    ai_diagnose_ticket: "AI diagnosis generated",
  };
  const label = labels[toolName] ?? toolName;
  // Show a brief snippet of the result (first 60 chars)
  const snippet = result.length > 60 ? result.slice(0, 60) + "…" : result;
  return `${label}: ${snippet}`;
}
