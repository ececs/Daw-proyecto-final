"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Cpu, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import api from "@/lib/api";

interface AIStatus {
  provider: string;
  model: string;
  fallback_available: boolean;
  fallback_model: string | null;
  last_error: string | null;
  last_error_at: string | null;
  action_count: number;
}

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export function AIStatusPanel() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    api.get<AIStatus>("/ai/status")
      .then((r) => setStatus(r.data))
      .catch(() => setStatus(null));
  }, []);

  if (!status) return null;

  const hasError = !!status.last_error;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 text-xs">
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-100 transition-colors rounded-lg"
      >
        <div className="flex items-center gap-2 text-slate-500">
          <Cpu className="w-3.5 h-3.5" />
          <span className="font-medium text-slate-600">
            {PROVIDER_LABELS[status.provider] ?? status.provider} · {status.model}
          </span>
          {status.fallback_available ? (
            <span className="text-teal-600 flex items-center gap-0.5">
              <CheckCircle2 className="w-3 h-3" /> fallback
            </span>
          ) : (
            <span className="text-slate-400">no fallback</span>
          )}
          {hasError && <AlertTriangle className="w-3 h-3 text-amber-500" />}
        </div>
        <div className="flex items-center gap-2 text-slate-400">
          <span>{status.action_count} actions</span>
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-slate-200 space-y-1.5 text-slate-500">
          <Row label="Provider" value={PROVIDER_LABELS[status.provider] ?? status.provider} />
          <Row label="Model" value={status.model} />
          <Row
            label="Fallback"
            value={
              status.fallback_available
                ? <span className="text-teal-600">{status.fallback_model} available</span>
                : <span className="text-slate-400">not configured</span>
            }
          />
          <Row label="Actions" value={String(status.action_count)} />
          {hasError ? (
            <div className="mt-2 rounded bg-amber-50 border border-amber-200 p-2">
              <p className="text-amber-700 font-medium flex items-center gap-1">
                <XCircle className="w-3 h-3" /> Last error
              </p>
              <p className="text-amber-600 mt-0.5 break-all">{status.last_error}</p>
              {status.last_error_at && (
                <p className="text-amber-400 mt-0.5">
                  {new Date(status.last_error_at).toLocaleTimeString()}
                </p>
              )}
            </div>
          ) : (
            <Row label="Last error" value={<span className="text-teal-600">none</span>} />
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
      <span className="text-slate-600 font-medium">{value}</span>
    </div>
  );
}
