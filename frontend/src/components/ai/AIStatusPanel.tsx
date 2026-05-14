"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, CheckCircle2, AlertTriangle, XCircle, ChevronDown, BarChart3, Clock3, Search, ThumbsUp } from "lucide-react";
import api from "@/lib/api";
import { AIStatsSummary, AIStatus, AIPreference } from "@/types";
import { getAIPreference, setAIPreference } from "@/lib/aiPreference";
import { getAISessionStart } from "@/lib/aiSession";

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export function AIStatusButton() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [stats, setStats] = useState<AIStatsSummary | null>(null);
  const [preference, setPreference] = useState<AIPreference>("auto");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const fetchAll = () => {
    const since = encodeURIComponent(getAISessionStart());
    Promise.all([
      api.get<AIStatus>(`/ai/status?since=${since}`),
      api.get<AIStatsSummary>("/ai/stats"),
    ])
      .then(([statusRes, statsRes]) => {
        setStatus(statusRes.data);
        setStats(statsRes.data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    setPreference(getAIPreference());
    fetchAll();
  }, []);

  // Refresh on open so count is fresh
  const handleOpen = () => {
    setOpen((v) => !v);
    fetchAll();
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

  const handlePreferenceChange = (value: AIPreference) => {
    setPreference(value);
    setAIPreference(value);
  };

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
        <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl shadow-lg border border-slate-200 z-50 overflow-hidden">
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
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Preference</span>
              <select
                value={preference}
                onChange={(e) => handlePreferenceChange(e.target.value as AIPreference)}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700"
                aria-label="AI model preference"
              >
                <option value="auto">Automatic</option>
                <option value="openai">GPT-4o-mini</option>
                <option value="google">Gemini 2.5 Flash</option>
              </select>
            </div>
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
            <Row label="Fallback used" value={<span className="font-mono">{status.fallback_count}</span>} />
            <Row label="Last surface" value={status.last_surface ?? "—"} />
          </div>

          {/* Usage stats */}
          <div className="px-4 py-3 space-y-2 text-xs">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Session usage</p>
            <Row label="Chat messages" value={<span className="font-mono">{status.chat_count}</span>} />
            <Row label="AI diagnoses" value={<span className="font-mono">{status.diagnoses_count}</span>} />
            <Row label="Tool actions" value={<span className="font-mono">{status.action_count}</span>} />
            <Row label="Avg latency" value={<span className="font-mono">{status.avg_latency_ms ? `${status.avg_latency_ms} ms` : "—"}</span>} />
            <Row label="Success / error" value={<span className="font-mono">{status.success_count} / {status.error_count}</span>} />
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
            <Row label="Last RAG source" value={<span className="font-mono">{status.last_rag_source}</span>} />
          </div>

          {stats && (
            <div className="px-4 py-3 space-y-2 text-xs border-t border-slate-100">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Historical stats</p>
              <Metric icon={BarChart3} label="Total runs" value={stats.total_runs} />
              <Metric icon={Clock3} label="Closed with AI" value={stats.tickets_closed_with_ai} />
              <Metric icon={Search} label="RAG hit rate" value={`${Math.min(100, Math.round(stats.rag_hit_rate * 100))}%`} />
              <Metric icon={ThumbsUp} label="Helped" value={`${Math.round(stats.helped_rate * 100)}%`} />
              <Row label="Total cost" value={`$${stats.total_estimated_cost_usd.toFixed(4)}`} />
              <Row label="Cost / run" value={`$${stats.avg_cost_per_run_usd.toFixed(4)}`} />
            </div>
          )}

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

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string | number;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5">
      <span className="flex items-center gap-1 text-slate-500">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </span>
      <span className="text-slate-700 font-medium">{value}</span>
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
