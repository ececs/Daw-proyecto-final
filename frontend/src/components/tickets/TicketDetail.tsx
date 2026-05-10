/**
 * TicketDetail — full ticket view with inline editing, comments, and attachments.
 *
 * Sections:
 *  1. Header: title (inline edit), status selector, priority selector, back button
 *  2. Sidebar: assignee picker, metadata (author, created, updated)
 *  3. Description: inline edit with textarea
 *  4. Comments: list (newest last) + add-comment form
 *  5. Attachments: upload dropzone + file list with download/delete
 *
 * All edits are sent via PATCH /tickets/{id} and the local state is updated
 * immediately (optimistic) so the UI feels instant.
 */

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, Clock, Paperclip, Trash2, Download, MessageSquare, Send, Loader2, Sparkles, RefreshCw, Globe, ExternalLink, Info, ChevronDown, ChevronUp, History, BarChart3, ThumbsUp, ThumbsDown,
} from "lucide-react";
import api from "@/lib/api";
import {
  Ticket, Comment, Attachment, TicketStatus, TicketPriority, User, TicketHistory, AITicketStats,
  ReplyDraftResponse,
} from "@/types";
import { getAuthToken } from "@/lib/auth";
import { getAIPreference } from "@/lib/aiPreference";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import {
  STATUS_LABELS,
  PRIORITY_CONFIG,
  timeAgo,
  formatDateTime,
  formatFileSize,
  getHostnameFromUrl,
  normalizeExternalUrl,
} from "@/lib/utils";
import { useUsers } from "@/hooks/useUsers";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { isRagEligible } from "@/lib/attachmentUtils";
import useNotificationStore from "@/stores/notificationStore";
import useAuthStore from "@/stores/authStore";

const STATUSES: TicketStatus[] = ["open", "in_progress", "in_review", "closed"];
const PRIORITIES: TicketPriority[] = ["low", "medium", "high", "critical"];

const fmt = (v: string | null) => v?.replace(/_/g, " ") ?? "—";

const HISTORY_LABELS: Record<string, (old: string | null, next: string | null) => string> = {
  created:     ()          => "created this ticket",
  status:      (o, n)      => `changed status from ${fmt(o)} to ${fmt(n)}`,
  priority:    (o, n)      => `changed priority from ${fmt(o)} to ${fmt(n)}`,
  assignee:    (o, n)      => n ? `assigned to ${n}` : `unassigned${o ? ` from ${o}` : ""}`,
  title:       ()          => "renamed the ticket",
  description: ()          => "updated the description",
  client_url:        (_, n) => n ? `set client URL to ${n}` : "removed client URL",
  attachment_added:  (_, n) => `uploaded attachment ${fmt(n)}`,
  attachment_removed:(o)    => `deleted attachment ${fmt(o)}`,
};

interface TicketDetailProps {
  ticketId: string;
}

export function TicketDetail({ ticketId }: TicketDetailProps) {
  const router = useRouter();
  const { users } = useUsers();
  const currentUser = useAuthStore((s) => s.user);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { refreshSignal, lastTicketId, deletedTicketId } = useNotificationStore();
  const { toast } = useToast();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [history, setHistory] = useState<TicketHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inline edit state
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const [descDraft, setDescDraft] = useState("");
  const [editingUrl, setEditingUrl] = useState(false);
  const [urlDraft, setUrlDraft] = useState("");
  const [editingSummary, setEditingSummary] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");

  const [showHistory, setShowHistory] = useState(false);

  // Comment form state
  const [commentText, setCommentText] = useState("");
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);
  const [resolutionNote, setResolutionNote] = useState("");
  const [isGeneratingReply, setIsGeneratingReply] = useState(false);
  const [replyDraftRunId, setReplyDraftRunId] = useState<string | null>(null);

  // Attachment upload state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  // AI Diagnosis state
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [aiDiagnosis, setAiDiagnosis] = useState<string | null>(null);
  const [aiDiagnosisRunId, setAiDiagnosisRunId] = useState<string | null>(null);
  const [isSubmittingDiagnosisFeedback, setIsSubmittingDiagnosisFeedback] = useState(false);
  const [diagnosisFeedback, setDiagnosisFeedback] = useState<boolean | null>(null);
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [showExtracted, setShowExtracted] = useState(false);
  const [extractedContent, setExtractedContent] = useState<string | null>(null);
  const [isRefreshingWeb, setIsRefreshingWeb] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [aiTicketStats, setAiTicketStats] = useState<AITicketStats | null>(null);
  const [isLoadingAITicketStats, setIsLoadingAITicketStats] = useState(false);
  const [confirmDeleteAttachmentId, setConfirmDeleteAttachmentId] = useState<string | null>(null);
  
  const commentTextareaRef = useRef<HTMLTextAreaElement>(null);
  const aiStatsRef = useRef<HTMLDivElement>(null);

  // Dynamic textarea resizing for main comment
  useEffect(() => {
    const textarea = commentTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [commentText]);

  const safeClientUrl = normalizeExternalUrl(ticket?.client_url);
  const clientHostname = getHostnameFromUrl(ticket?.client_url);


  const refreshWebContext = async () => {
    if (!ticket?.client_url) return;
    
    setIsRefreshingWeb(true);
    try {
      await api.post(`/tickets/${ticketId}/web-scrape-refresh`);
      // We don't call fetchData here because the WebSocket will trigger it
      // once the background scraping task is done.
    } catch (err) {
      console.error("Failed to trigger scrape refresh", err);
      setIsRefreshingWeb(false);
    }
  };

  // ── Fetch ticket, comments, attachments ──────────────────────────────────

  useEffect(() => {
    fetchData();
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  // AI stats load lazily when the stats section scrolls into view, so they
  // don't compete with ticket/comments/attachments on the critical first load.
  useEffect(() => {
    const el = aiStatsRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          observer.disconnect();
          void fetchAITicketStats();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Real-time refresh listener (WebSockets)
  useEffect(() => {
    if (refreshSignal > 0 && lastTicketId === ticketId) {
      fetchData(true);
      setIsRefreshingWeb(false);
    }
  }, [refreshSignal, lastTicketId, ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  // If this ticket was deleted from another tab, navigate away
  useEffect(() => {
    if (deletedTicketId && deletedTicketId === ticketId) {
      router.push("/board");
    }
  }, [deletedTicketId, ticketId]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchData = async (background = false) => {
    if (!ticketId || ticketId === "None" || ticketId === "undefined") return;
    if (!background) setIsLoading(true);
    try {
      // Load the critical ticket UI first; slower auxiliary blocks can hydrate afterwards.
      const [ticketRes, commentsRes, attachmentsRes] = await Promise.all([
        api.get<Ticket>(`/tickets/${ticketId}`),
        api.get<Comment[]>(`/tickets/${ticketId}/comments`),
        api.get<Attachment[]>(`/tickets/${ticketId}/attachments`).catch(() => ({ data: [] as Attachment[] })),
      ]);
      setTicket(ticketRes.data);
      setComments(commentsRes.data);
      setAttachments(attachmentsRes.data);

      // Secondary data does not need to block the initial paint of the detail page.
      void Promise.all([
        api.get<{ content: string | null }>(`/tickets/${ticketId}/web-context`).catch(() => ({ data: { content: null } })),
        api.get<TicketHistory[]>(`/tickets/${ticketId}/history`).catch(() => ({ data: [] as TicketHistory[] })),
      ]).then(([webCtxRes, historyRes]) => {
        setExtractedContent(webCtxRes.data.content);
        setHistory(historyRes.data);
      });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status;
      const detail = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.data?.detail;
      setError(
        status === 404
          ? "Ticket not found"
          : detail
          ? `Error: ${detail}`
          : `Failed to load ticket (${status ?? "network error"})`
      );
    } finally {
      if (!background) setIsLoading(false);
    }
  };

  const fetchAITicketStats = useCallback(async () => {
    if (!ticketId || ticketId === "None" || ticketId === "undefined") return;
    setIsLoadingAITicketStats(true);
    try {
      const { data } = await api.get<AITicketStats>(`/ai/stats/tickets/${ticketId}`);
      setAiTicketStats(data);
    } catch (err) {
      console.error("Failed to load AI ticket stats", err);
    } finally {
      setIsLoadingAITicketStats(false);
    }
  }, [ticketId]);

  // ── Ticket field updates ─────────────────────────────────────────────────

  const patchTicket = async (data: Partial<Ticket>) => {
    if (!ticket) return;

    // Optimistic Update: update UI immediately
    const previousTicket = { ...ticket };
    setTicket({ ...ticket, ...data } as Ticket);

    try {
      const { data: updated } = await api.patch<Ticket>(`/tickets/${ticketId}`, data);
      setTicket(updated);
      toast({ title: "Cambios guardados", description: "El ticket se ha actualizado correctamente." });
    } catch (error) {
      console.error("Failed to patch ticket", error);
      setTicket(previousTicket);
      toast({ title: "Error al guardar", description: "No se pudieron guardar los cambios. Inténtalo de nuevo.", variant: "destructive" });
    }
  };

  const handleStatusChange = (status: TicketStatus) => patchTicket({ status });
  const handlePriorityChange = (priority: TicketPriority) => patchTicket({ priority });
  const handleAssigneeChange = (assigneeId: string) =>
    patchTicket({ assignee_id: assigneeId || null } as Partial<Ticket>);

  const saveTitle = async () => {
    if (titleDraft.trim() && titleDraft !== ticket?.title) {
      await patchTicket({ title: titleDraft.trim() });
    }
    setEditingTitle(false);
  };

  const saveDesc = async () => {
    await patchTicket({ description: descDraft });
    setEditingDesc(false);
  };

  const saveUrl = async () => {
    if (urlDraft !== ticket?.client_url) {
      await patchTicket({ client_url: urlDraft.trim() || null });
    }
    setEditingUrl(false);
  };

  const saveSummary = async () => {
    if (summaryDraft !== ticket?.client_summary) {
      await patchTicket({ client_summary: summaryDraft.trim() || null });
    }
    setEditingSummary(false);
  };

  // ── Comments ─────────────────────────────────────────────────────────────

  const submitComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    setIsSubmittingComment(true);
    try {
      const { data: newComment } = await api.post<Comment>(
        `/tickets/${ticketId}/comments`,
        { content: commentText.trim() }
      );
      setComments((prev) => [...prev, newComment]);
      setCommentText("");
      toast({ title: "Comentario enviado" });
    } catch {
      toast({ title: "Error al enviar comentario", variant: "destructive" });
    } finally {
      setIsSubmittingComment(false);
    }
  };

  const deleteComment = async (commentId: string) => {
    if (!confirm("Delete this comment?")) return;
    await api.delete(`/tickets/${ticketId}/comments/${commentId}`);
    setComments((prev) => prev.filter((c) => c.id !== commentId));
  };

  const handleGenerateReplyDraft = async () => {
    const note = resolutionNote.trim();
    if (!note || isGeneratingReply) return;

    // Never overwrite a human draft silently.
    if (commentText.trim() && !confirm("This will replace the current comment draft. Continue?")) {
      return;
    }

    setIsGeneratingReply(true);
    try {
      const preferredProvider = getAIPreference();
      const { data } = await api.post<ReplyDraftResponse>(`/tickets/${ticketId}/reply-draft`, {
        resolution_note: note,
        preferred_provider: preferredProvider,
      });
      // Reuse the existing manual comment flow: AI only prepares the draft.
      setCommentText(data.draft);
      setReplyDraftRunId(data.ai_run_id);
      toast({
        title: "Borrador generado",
        description: "La IA ha preparado un comentario que puedes revisar antes de enviarlo.",
      });
      void fetchAITicketStats();
    } catch (error) {
      console.error("Failed to generate AI reply draft", error);
      toast({
        title: "Error al generar borrador",
        description: "No se pudo generar el borrador de respuesta. El comentario actual no se ha modificado.",
        variant: "destructive",
      });
    } finally {
      setIsGeneratingReply(false);
    }
  };

  // ── Attachments ──────────────────────────────────────────────────────────

  const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB — must match backend MAX_ATTACHMENT_SIZE_MB

  const uploadFile = async (file: File) => {
    if (file.size > MAX_FILE_BYTES) {
      setUploadError("File exceeds the 10 MB limit");
      return;
    }
    setIsUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data: att } = await api.post<Attachment>(
        `/tickets/${ticketId}/attachments`,
        form,
        {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 120000, // 2 min — large files need more than the default 10 s
        }
      );
      setAttachments((prev) => [...prev, att]);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setUploadError(axiosErr.response?.data?.detail ?? "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const deleteAttachment = (attId: string) => {
    setConfirmDeleteAttachmentId(attId);
  };

  const handleConfirmDeleteAttachment = async () => {
    if (!confirmDeleteAttachmentId) return;
    const attId = confirmDeleteAttachmentId;
    setConfirmDeleteAttachmentId(null);
    await api.delete(`/tickets/${ticketId}/attachments/${attId}`);
    setAttachments((prev) => prev.filter((a) => a.id !== attId));
  };

  const toggleAttachmentRag = async (attId: string, currentStatus: boolean) => {
    try {
      const newStatus = !currentStatus;
      const res = await api.patch<Attachment>(
        `/tickets/${ticketId}/attachments/${attId}?use_for_rag=${newStatus}`
      );
      setAttachments((prev) =>
        prev.map((a) => (a.id === attId ? { ...a, use_for_rag: res.data.use_for_rag } : a))
      );
      toast({
        title: newStatus ? "Enabled for RAG" : "Disabled from RAG",
        description: newStatus
          ? "The AI assistant will now use this document as context."
          : "The AI assistant will no longer use this document as context.",
      });
    } catch (err) {
      toast({
        title: "Failed to update RAG",
        description: "Could not update the attachment status.",
        variant: "destructive",
      });
    }
  };


  // ── AI Diagnosis ─────────────────────────────────────────────────────────
  
  const handleAIDiagnose = async (force = false) => {
    // If we already have a diagnosis and we're not forcing a refresh, just toggle visibility
    if (aiDiagnosis && !force) {
      setShowDiagnosis(!showDiagnosis);
      return;
    }

    setIsDiagnosing(true);
    setAiDiagnosis(""); // Initialize as empty string for streaming
    setAiDiagnosisRunId(null);
    setDiagnosisFeedback(null);
    setShowDiagnosis(true);
    
    try {
      const token = getAuthToken();
      
      const preferredProvider = getAIPreference();
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/tickets/${ticketId}/diagnosis?preferred_provider=${preferredProvider}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (!response.ok) throw new Error("Failed to connect to AI service");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) throw new Error("ReadableStream not supported");

      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;
          try {
            const event = JSON.parse(line) as { type: string; content?: string; ai_run_id?: string };
            if (event.type === "session" && event.ai_run_id) {
              setAiDiagnosisRunId(event.ai_run_id);
            } else if (event.type === "token" && event.content) {
              setAiDiagnosis((prev) => (prev || "") + event.content);
            } else if (event.type === "error" && event.content) {
              setAiDiagnosis(event.content);
            }
          } catch {
            // Ignore malformed chunks
          }
        }
      }
      void fetchAITicketStats();
    } catch (err: unknown) {
      console.error("AI Diagnosis failed", err);
      setAiDiagnosis("*(Error: Could not connect to the AI service for real-time diagnosis)*");
    } finally {
      setIsDiagnosing(false);
    }
  };

  const submitDiagnosisFeedback = async (helped: boolean) => {
    if (!aiDiagnosisRunId || isSubmittingDiagnosisFeedback) return;
    setIsSubmittingDiagnosisFeedback(true);
    try {
      await api.post("/ai/feedback", {
        ai_run_id: aiDiagnosisRunId,
        helped,
        label: helped ? "helped_close" : "did_not_help",
      });
      setDiagnosisFeedback(helped);
      void fetchAITicketStats();
    } catch (error) {
      console.error("Failed to submit diagnosis feedback", error);
    } finally {
      setIsSubmittingDiagnosisFeedback(false);
    }
  };

  const handleDeleteTicket = async () => {
    try {
      await api.delete(`/tickets/${ticketId}`);
      toast({
        title: "Ticket deleted",
        description: "The ticket was permanently removed.",
      });
      router.push("/board");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Could not delete the ticket.";
      toast({
        title: "Deletion failed",
        description: detail,
        variant: "destructive",
      });
    } finally {
      setConfirmDeleteOpen(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="p-6">
        <p className="text-red-600">{error ?? "Ticket not found"}</p>
        <button onClick={() => router.push("/board")} className="mt-2 text-blue-600 hover:underline text-sm">
          Back to board
        </button>
      </div>
    );
  }

  const canDeleteTicket = currentUser?.id === ticket.author_id;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Back */}
      <button
        onClick={() => router.push("/board")}
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-5 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to board
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
        {/* ── Main column ── */}
        <div className="space-y-6">
          {/* Title */}
          <div>
            {editingTitle ? (
              <div className="flex gap-2">
                <input
                  autoFocus
                  aria-label="Título del ticket"
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onBlur={saveTitle}
                  onKeyDown={(e) => e.key === "Enter" && saveTitle()}
                  className="flex-1 text-2xl font-bold border-b-2 border-blue-500 outline-none bg-transparent text-slate-900"
                />
              </div>
            ) : (
              <h1
                onClick={() => { setTitleDraft(ticket.title); setEditingTitle(true); }}
                className="text-2xl font-bold text-slate-900 cursor-text hover:text-blue-600 transition-colors"
                title="Click to edit"
              >
                {ticket.title}
              </h1>
            )}

            {/* Status + priority row */}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select
                aria-label="Estado del ticket"
                value={ticket.status}
                onChange={(e) => handleStatusChange(e.target.value as TicketStatus)}
                className="text-sm border border-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                ))}
              </select>

              <select
                aria-label="Prioridad del ticket"
                value={ticket.priority}
                onChange={(e) => handlePriorityChange(e.target.value as TicketPriority)}
                className="text-sm border border-slate-200 rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{PRIORITY_CONFIG[p].label}</option>
                ))}
              </select>

              <Badge variant={ticket.status}>
                {STATUS_LABELS[ticket.status]}
              </Badge>

              {/* AI Diagnosis Button */}
              <button
                onClick={() => handleAIDiagnose()}
                disabled={isDiagnosing}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700 transition-all shadow-sm disabled:opacity-50"
              >
                {isDiagnosing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                Diagnóstico IA
              </button>

              {canDeleteTicket && (
                <button
                  onClick={() => setConfirmDeleteOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold text-red-600 border border-red-200 hover:bg-red-50 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete ticket
                </button>
              )}
            </div>
          </div>

          {/* AI Diagnosis Results */}
          {aiDiagnosis && showDiagnosis && (
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 rounded-xl p-4 shadow-sm relative overflow-hidden group animate-in fade-in slide-in-from-top-2 duration-300">
              <div className="absolute top-0 right-0 p-2 flex gap-2">
                <button
                  onClick={() => handleAIDiagnose(true)}
                  disabled={isDiagnosing}
                  aria-label="Regenerar diagnóstico"
                  className="p-1 rounded hover:bg-blue-100 text-blue-400 hover:text-blue-600 transition-colors"
                  title="Regenerar diagnóstico"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isDiagnosing ? "animate-spin" : ""}`} />
                </button>
                <Sparkles className="w-4 h-4 text-blue-400 opacity-20 group-hover:opacity-100 transition-opacity" />
              </div>
              <h3 className="text-xs font-bold text-blue-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                Análisis Técnico IA
              </h3>
              <p className="text-sm text-slate-700 leading-relaxed italic whitespace-pre-wrap">
                {aiDiagnosis}
              </p>
              {aiDiagnosisRunId && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] text-slate-500">¿Te ayudó este diagnóstico?</span>
                  <button
                    onClick={() => submitDiagnosisFeedback(true)}
                    disabled={diagnosisFeedback !== null || isSubmittingDiagnosisFeedback}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition-colors ${
                      diagnosisFeedback === true
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-white text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"
                    } disabled:opacity-70`}
                  >
                    {isSubmittingDiagnosisFeedback ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3 h-3" />}
                    Ayudó
                  </button>
                  <button
                    onClick={() => submitDiagnosisFeedback(false)}
                    disabled={diagnosisFeedback !== null || isSubmittingDiagnosisFeedback}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition-colors ${
                      diagnosisFeedback === false
                        ? "bg-rose-100 text-rose-700"
                        : "bg-white text-slate-600 hover:bg-rose-50 hover:text-rose-700"
                    } disabled:opacity-70`}
                  >
                    {isSubmittingDiagnosisFeedback ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsDown className="w-3 h-3" />}
                    No ayudó
                  </button>
                </div>
              )}
              <div className="mt-3 flex justify-end">
                <button 
                  onClick={() => setShowDiagnosis(false)}
                  className="text-[10px] text-blue-400 hover:text-blue-600 font-medium"
                >
                  Cerrar análisis
                </button>
              </div>
            </div>
          )}



          {/* Client URL Context */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <Globe className="w-4 h-4 text-blue-500" /> Web del Cliente
              </h2>
              <div className="flex items-center gap-3">
                {ticket.client_url && (
                  <button
                    onClick={refreshWebContext}
                    disabled={isRefreshingWeb}
                    aria-label="Actualizar análisis web"
                    className={`p-1 rounded-full hover:bg-slate-100 transition-colors ${isRefreshingWeb ? "text-blue-500" : "text-slate-400"}`}
                    title="Actualizar análisis de la web"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingWeb ? "animate-spin" : ""}`} />
                  </button>
                )}
                {safeClientUrl && !editingUrl && (
                  <a 
                    href={safeClientUrl}
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                  >
                    Visitar <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
            
            {editingUrl ? (
              <div className="flex gap-2">
                <input
                  autoFocus
                  aria-label="URL del cliente"
                  value={urlDraft}
                  onChange={(e) => setUrlDraft(e.target.value)}
                  placeholder="https://example.com"
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button 
                  onClick={saveUrl}
                  className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  OK
                </button>
                <button 
                  onClick={() => setEditingUrl(false)}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  X
                </button>
              </div>
            ) : (
              <p 
                onClick={() => { setUrlDraft(ticket.client_url ?? ""); setEditingUrl(true); }}
                className="text-sm text-slate-600 cursor-text hover:bg-slate-50 rounded-lg p-2 -m-2 transition-colors flex items-center gap-2"
                title="Click para editar URL"
              >
                {ticket.client_url ? (
                  <span className="truncate">{ticket.client_url}</span>
                ) : (
                  <span className="text-slate-400 italic">No hay web vinculada. Haz clic para añadir una.</span>
                )}
              </p>
            )}
            {ticket.client_url && (
              <p className="text-[10px] text-slate-400 mt-2">
                La IA usa esta web para enriquecer el diagnóstico técnico.
              </p>
            )}

            {/* AI Extracted Context Collapsible */}
            {ticket.client_url && extractedContent && (
              <div className="mt-3 border border-blue-100 bg-blue-50/30 rounded-lg overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowExtracted(!showExtracted)}
                  className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-medium text-blue-700 hover:bg-blue-50 transition-colors"
                >
                  <span className="flex items-center gap-1.5">
                    <Sparkles className="w-3 h-3" />
                    Análisis automático de {clientHostname ?? "la web del cliente"}
                  </span>
                  {showExtracted ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
                
                {showExtracted && (
                  <div className="px-3 pb-3 pt-1 text-[11px] text-slate-600 leading-relaxed italic border-t border-blue-100 animate-in slide-in-from-top-2">
                    {extractedContent}
                    <div className="mt-2 text-[9px] text-blue-500 font-semibold uppercase tracking-wider">
                      Contexto extraído por la IA
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {ticket.client_url && !extractedContent && (
              <div className="mt-2 text-[9px] text-slate-400 italic flex items-center gap-1 px-1">
                <Clock className="w-2.5 h-2.5" /> 
                Análisis automático pendiente o en curso...
              </div>
            )}
          </div>

          {/* Client Summary Context */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
              <Info className="w-4 h-4 text-indigo-500" /> Perfil del Cliente
            </h2>
            
            {editingSummary ? (
              <div className="space-y-2">
                <textarea
                  autoFocus
                  value={summaryDraft}
                  onChange={(e) => setSummaryDraft(e.target.value)}
                  placeholder="Describe al cliente, tecnologías, importancia..."
                  rows={3}
                  className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
                <div className="flex gap-2">
                  <button 
                    onClick={saveSummary}
                    className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    Guardar
                  </button>
                  <button 
                    onClick={() => setEditingSummary(false)}
                    className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ) : (
              <p 
                onClick={() => { setSummaryDraft(ticket.client_summary ?? ""); setEditingSummary(true); }}
                className="text-sm text-slate-600 cursor-text hover:bg-slate-50 rounded-lg p-2 -m-2 transition-colors min-h-[40px]"
                title="Click para editar resumen"
              >
                {ticket.client_summary ? (
                  ticket.client_summary
                ) : (
                  <span className="text-slate-400 italic">Sin resumen manual. Haz clic para añadir notas sobre el cliente.</span>
                )}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-2">Description</h2>
            {editingDesc ? (
              <div className="space-y-2">
                <textarea
                  autoFocus
                  value={descDraft}
                  onChange={(e) => setDescDraft(e.target.value)}
                  rows={4}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
                <div className="flex gap-2">
                  <button onClick={saveDesc} className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                    Save
                  </button>
                  <button onClick={() => setEditingDesc(false)} className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p
                onClick={() => { setDescDraft(ticket.description ?? ""); setEditingDesc(true); }}
                className="text-sm text-slate-600 whitespace-pre-wrap cursor-text hover:bg-slate-50 rounded-lg p-2 -m-2 transition-colors min-h-[60px]"
                title="Click to edit"
              >
                {ticket.description || <span className="text-slate-400 italic">No description. Click to add one.</span>}
              </p>
            )}
          </div>

          {/* Attachments */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <Paperclip className="w-4 h-4" /> Attachments ({attachments.length})
              </h2>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50 transition-colors"
              >
                {isUploading ? "Uploading..." : "Upload file"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])}
              />
            </div>

            {uploadError && (
              <p className="text-xs text-red-600 mb-2">{uploadError}</p>
            )}

            {attachments.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">No attachments yet</p>
            ) : (
              <ul className="space-y-2">
                {attachments.map((att) => (
                  <li key={att.id} className={`flex items-center justify-between gap-3 p-2.5 rounded-lg border transition-all duration-200 ${
                    att.use_for_rag 
                      ? "bg-teal-50/40 border-teal-200/60 shadow-sm" 
                      : "border-slate-100 hover:bg-slate-50 hover:border-slate-200"
                  } group`}>
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`p-2 rounded-lg shrink-0 ${
                        att.use_for_rag ? "bg-teal-100/80 text-teal-600 animate-pulse" : "bg-slate-100 text-slate-500"
                      }`}>
                        <Paperclip className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p className={`text-sm font-medium truncate ${
                            att.use_for_rag ? "text-teal-900 font-semibold" : "text-slate-700"
                          }`}>{att.filename}</p>
                          {att.use_for_rag && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-teal-100 text-teal-800 border border-teal-200">
                              <Sparkles className="w-2.5 h-2.5 text-teal-600" /> RAG Active
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400">{formatFileSize(att.size_bytes)}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-3 shrink-0">
                      {/* Checkbox for RAG — only for indexable types */}
                      {isRagEligible(att.mime_type) && (
                        <label className="flex items-center gap-1.5 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={!!att.use_for_rag}
                            onChange={() => toggleAttachmentRag(att.id, !!att.use_for_rag)}
                            className="w-4 h-4 rounded text-teal-600 border-slate-300 focus:ring-teal-500 cursor-pointer accent-teal-600 transition-colors"
                          />
                          <span className={`text-xs font-medium transition-colors ${
                            att.use_for_rag ? "text-teal-700 font-semibold" : "text-slate-400 hover:text-slate-600"
                          }`}>
                            Use for RAG
                          </span>
                        </label>
                      )}

                      {/* Download and Delete actions */}
                      <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                        {att.download_url && (
                          <a
                            href={att.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Download ${att.filename}`}
                            className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors"
                            title="Download"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </a>
                        )}
                        <button
                          onClick={() => deleteAttachment(att.id)}
                          aria-label={`Delete ${att.filename}`}
                          className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Comments */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-1.5">
              <MessageSquare className="w-4 h-4" /> Comments ({comments.length})
            </h2>

            {/* Comment list */}
            <div className="space-y-4 mb-4">
              {comments.length === 0 && (
                <p className="text-sm text-slate-400 text-center py-2">No comments yet. Be the first!</p>
              )}
              {comments.map((c) => (
                <div key={c.id} className="flex gap-3 group">
                  <UserAvatar
                    src={c.author?.avatar_url}
                    name={c.author?.name ?? "?"}
                    size="sm"
                    className="mt-0.5"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-slate-700">{c.author?.name ?? "Unknown"}</span>
                      <span className="text-xs text-slate-400">{formatDateTime(c.created_at)}</span>
                    </div>
                    <p className="text-sm text-slate-600 whitespace-pre-wrap">{c.content}</p>
                  </div>
                  <button
                    onClick={() => deleteComment(c.id)}
                    aria-label="Eliminar comentario"
                    className="p-1.5 rounded hover:bg-red-50 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all self-start mt-0.5"
                    title="Delete comment"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>

            {/* Add comment form */}
            <div className="mb-4 rounded-xl border border-blue-100 bg-blue-50/50 p-3">
              <div className="mb-2 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-blue-600" />
                <h3 className="text-xs font-semibold uppercase tracking-wide text-blue-700">AI Reply</h3>
              </div>
              <p className="mb-3 text-xs text-slate-600">
                Escribe un resumen corto de la solución y la IA preparará un borrador profesional en la caja de comentario. El envío seguirá siendo manual.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <textarea
                  aria-label="Resumen corto de la solución"
                  value={resolutionNote}
                  onChange={(e) => setResolutionNote(e.target.value)}
                  placeholder="Ej. Se corrigió el DNS del subdominio y se invalidó la caché de Cloudflare."
                  rows={2}
                  className="min-h-[72px] flex-1 rounded-lg border border-blue-100 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
                <button
                  type="button"
                  onClick={handleGenerateReplyDraft}
                  disabled={isGeneratingReply || !resolutionNote.trim()}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 sm:self-end"
                >
                  {isGeneratingReply ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Generar borrador
                </button>
              </div>
              {replyDraftRunId && (
                <p className="mt-2 text-[11px] text-slate-500">
                  Borrador IA preparado. Revísalo y edítalo libremente antes de publicarlo.
                </p>
              )}
            </div>

            <form onSubmit={submitComment} className="flex gap-2">
              <textarea
                aria-label="Escribir un comentario"
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                ref={commentTextareaRef}
                placeholder="Add a comment..."
                rows={2}
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none max-h-36 overflow-y-auto"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitComment(e as unknown as React.FormEvent);
                }}
              />
              <button
                type="submit"
                disabled={isSubmittingComment || !commentText.trim()}
                aria-label="Enviar comentario"
                className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors self-end"
                title="Send (Ctrl+Enter)"
              >
                {isSubmittingComment ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </form>
          </div>

          <div ref={aiStatsRef} className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4 text-blue-500" /> Impacto de IA en este ticket
              </h2>
              {isLoadingAITicketStats && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
            </div>
            {aiTicketStats ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Diagnósticos</p>
                  <p className="text-sm font-semibold text-slate-800">{aiTicketStats.diagnosis_runs}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Chats ligados</p>
                  <p className="text-sm font-semibold text-slate-800">{aiTicketStats.chat_runs}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Consultas RAG</p>
                  <p className="text-sm font-semibold text-slate-800">{aiTicketStats.rag_queries_count}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Hit rate RAG</p>
                  <p className="text-sm font-semibold text-slate-800">{Math.round(aiTicketStats.rag_hit_rate * 100)}%</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Feedback positivo</p>
                  <p className="text-sm font-semibold text-slate-800">{aiTicketStats.positive_feedback_count}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <p className="text-slate-500">Coste estimado</p>
                  <p className="text-sm font-semibold text-slate-800">${aiTicketStats.estimated_cost_usd.toFixed(4)}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Todavía no hay actividad de IA asociada a este ticket.</p>
            )}
            {aiTicketStats && (
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                <span>
                  Último uso: {aiTicketStats.last_ai_used_at ? formatDateTime(aiTicketStats.last_ai_used_at) : "—"}
                </span>
                <span>
                  Tiempo hasta cierre: {aiTicketStats.time_to_close_hours !== null ? `${aiTicketStats.time_to_close_hours} h` : "Abierto"}
                </span>
                <span>
                  Ayuda global: {aiTicketStats.helped === null ? "Sin feedback" : aiTicketStats.helped ? "Positiva" : "Negativa"}
                </span>
              </div>
            )}
          </div>

          {/* Activity */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
            >
              <span className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <History className="w-4 h-4" />
                Activity
                {history.length > 0 && (
                  <span className="ml-1 text-xs font-normal text-slate-400">({history.length})</span>
                )}
              </span>
              {showHistory ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>

            {showHistory && (
              <div className="px-4 pb-4 border-t border-slate-100">
                {history.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-4">No activity yet</p>
                ) : (
                  <ol className="relative border-l border-slate-100 space-y-4 ml-2 mt-4">
                    {history.map((entry) => (
                      <li key={entry.id} className="pl-4">
                        <span className="absolute -left-1 w-2 h-2 rounded-full bg-slate-300 mt-1.5" />
                        <p className="text-sm text-slate-700">
                          <span className="font-medium">{entry.actor?.name ?? "Someone"}</span>{" "}
                          {HISTORY_LABELS[entry.field]?.(entry.old_value, entry.new_value) ?? `updated ${entry.field}`}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">{formatDateTime(entry.created_at)}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Sidebar ── */}
        <aside className="space-y-4">
          {/* Assignee */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Assignee</h3>
            <select
              value={ticket.assignee_id ?? ""}
              onChange={(e) => handleAssigneeChange(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Unassigned</option>
              {users.map((u: User) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>

            {ticket.assignee && (
              <div className="flex items-center gap-2 mt-3">
                <UserAvatar 
                  src={ticket.assignee.avatar_url} 
                  name={ticket.assignee.name} 
                  size="sm" 
                />
                <div>
                  <p className="text-sm font-medium text-slate-700">{ticket.assignee.name}</p>
                  <p className="text-xs text-slate-400">{ticket.assignee.email}</p>
                </div>
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Details</h3>

            <div>
              <p className="text-xs text-slate-400">Author</p>
              <p className="text-sm text-slate-700">{ticket.author?.name ?? "Unknown"}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Created</p>
              <p className="text-sm text-slate-700">{timeAgo(ticket.created_at)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Last updated</p>
              <p className="text-sm text-slate-700">{timeAgo(ticket.updated_at)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400">Ticket ID</p>
              <p className="text-xs text-slate-500 font-mono">{ticket.id}</p>
            </div>
          </div>
        </aside>
      </div>
      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete ticket"
        description="This action cannot be undone. The ticket and all its comments and attachments will be permanently removed."
        confirmLabel="Delete ticket"
        onConfirm={handleDeleteTicket}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
      <ConfirmDialog
        open={confirmDeleteAttachmentId !== null}
        title="Delete attachment"
        description="The file will be permanently deleted. This action cannot be undone."
        confirmLabel="Delete"
        onConfirm={handleConfirmDeleteAttachment}
        onCancel={() => setConfirmDeleteAttachmentId(null)}
      />
    </div>
  );
}
