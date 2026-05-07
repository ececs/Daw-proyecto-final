"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, CheckCircle2, AlertTriangle, XCircle, ChevronDown } from "lucide-react";
import api from "@/lib/api";

interface AIStatus {
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
}

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export function AIStatusButton() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<AIStatus>("/ai/status")
      .then((r) => setStatus(r.data))
      .catch(() => {});
  }, []);

  // Refresh on open so count is fresh
  const handleOpen = () => {
    setOpen((v) => !v);
    api.get<AIStatus>("/ai/status")
      .then((r) => setStatus(r.data))
      .catch(() => {});
  };

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!status) return null;

  const hasError = !!status.last_error;
  const isHealthy = !hasError && status.model !== "unknown";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={handleOpen}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
          open
            ? "bg-slate-100 text-slate-700"
            : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        }`}
        aria-label="AI system status"
        title="AI status"
      >
        <Activity className={`w-4 h-4 ${hasError ? "text-amber-500" : isHealthy ? "text-teal-500" : "text-slate-400"}`} />
        <span className="hidden sm:block text-xs">{status.model !== "unknown" ? status.model : "AI"}</span>
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-72 bg-white rounded-xl shadow-lg border border-slate-200 z-50 overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">AI Status</p>
            {isHealthy && !hasError
              ? <span className="flex items-center gap-1 text-xs text-teal-600"><CheckCircle2 className="w-3.5 h-3.5" /> Operational</span>
              : <span className="flex items-center gap-1 text-xs text-amber-500"><AlertTriangle className="w-3.5 h-3.5" /> Degraded</span>
            }
          </div>

          {/* Model info */}
          <div className="px-4 py-3 space-y-2 text-xs border-b border-slate-100">
            <Row label="Provider" value={PROVIDER_LABELS[status.provider] ?? status.provider} />
            <Row label="Model" value={status.model} />
            <Row
              label="Fallback"
              value={
                status.fallback_available
                  ? <span className="text-teal-600">{status.fallback_model} ✓</span>
                  : <span className="text-slate-400">not configured</span>
              }
            />
          </div>

          {/* Usage stats */}
          <div className="px-4 py-3 space-y-2 text-xs">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Session usage</p>
            <Row label="Chat messages" value={<span className="font-mono">{status.chat_count}</span>} />
            <Row label="AI diagnoses" value={<span className="font-mono">{status.diagnoses_count}</span>} />
            <Row label="Tool actions" value={<span className="font-mono">{status.action_count}</span>} />
            <Row
              label="RAG queries"
              value={
                <span className="font-mono">
                  {status.rag_queries_count}
                  {status.rag_queries_count > 0 && (
                    <span className="text-slate-400 ml-1">
                      ({Math.round(status.rag_hits_count / status.rag_queries_count * 100)}% hits)
                    </span>
                  )}
                </span>
              }
            />
          </div>

          {/* Last error */}
          {hasError && (
            <div className="mx-4 mb-3 rounded-lg bg-amber-50 border border-amber-200 p-2.5 text-xs">
              <p className="text-amber-700 font-medium flex items-center gap-1 mb-1">
                <XCircle className="w-3.5 h-3.5" /> Last error
              </p>
              <p className="text-amber-600 break-all">{status.last_error}</p>
              {status.last_error_at && (
                <p className="text-amber-400 mt-1">{new Date(status.last_error_at).toLocaleTimeString()}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-700 font-medium">{value}</span>
    </div>
  );
}
