"use client";

import { useState, useEffect, useRef } from "react";
import { getReasoning, API_BASE, type ReasoningStep } from "@/lib/api";

const STAGE_ICONS: Record<string, string> = {
  search: "🔍",
  synthesis: "🧠",
  report: "📝",
  evaluation: "✅",
};

const STAGE_COLORS: Record<string, string> = {
  search: "border-blue-700 bg-blue-900/20",
  synthesis: "border-purple-700 bg-purple-900/20",
  report: "border-amber-700 bg-amber-900/20",
  evaluation: "border-cyan-700 bg-cyan-900/20",
};

function StepCard({ step }: { step: ReasoningStep }) {
  const [expanded, setExpanded] = useState(false);
  const icon = STAGE_ICONS[step.stage] || "📋";
  const colorClass = STAGE_COLORS[step.stage] || "border-gray-700 bg-gray-900/20";

  const renderData = () => {
    const data = step.data;

    // String list (search queries, report outline)
    if (Array.isArray(data) && data.length > 0 && typeof data[0] === "string") {
      return (
        <ul className="space-y-1 text-xs text-gray-300">
          {(data as string[]).map((item, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-gray-500 shrink-0">{i + 1}.</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      );
    }

    // Plain string (evaluation reasoning)
    if (typeof data === "string") {
      return <p className="text-xs text-gray-300 whitespace-pre-wrap">{data}</p>;
    }

    // Object arrays (sources, evidence, themes, contradictions)
    if (Array.isArray(data) && data.length > 0 && typeof data[0] === "object") {
      return (
        <div className="space-y-2">
          {(data as Record<string, unknown>[]).map((item, i) => (
            <div
              key={i}
              className="rounded border border-gray-700/50 bg-gray-800/30 p-2 text-xs space-y-1"
            >
              {Object.entries(item).map(([key, value]) => {
                if (value === "" || value === null || (Array.isArray(value) && value.length === 0))
                  return null;
                return (
                  <div key={key} className="flex gap-2">
                    <span className="text-gray-500 shrink-0 font-mono">
                      {key}:
                    </span>
                    <span className="text-gray-300 break-all">
                      {typeof value === "string"
                        ? value.length > 200
                          ? value.slice(0, 200) + "…"
                          : value
                        : JSON.stringify(value)}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      );
    }

    return (
      <pre className="text-xs text-gray-400 overflow-x-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    );
  };

  return (
    <div className={`rounded-lg border p-3 ${colorClass}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between gap-2 text-left"
      >
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <div>
            <p className="text-sm font-medium text-gray-200">{step.title}</p>
            <p className="text-xs text-gray-400">{step.description}</p>
          </div>
        </div>
        <span className="text-gray-500 text-xs shrink-0">
          {expanded ? "▲" : "▼"}
        </span>
      </button>
      {expanded && <div className="mt-3 pt-3 border-t border-gray-700/50">{renderData()}</div>}
    </div>
  );
}

export default function ReasoningPanel({ jobId }: { jobId: string }) {
  const [steps, setSteps] = useState<ReasoningStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [available, setAvailable] = useState(false);
  const [live, setLive] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Map SSE event to a ReasoningStep
  function mapEventToStep(event: { type: string; data: Record<string, unknown> }): ReasoningStep | null {
    const t = event.type;
    const d = event.data;
    switch (t) {
      case "stage_started":
        return { stage: d.stage as string, title: `${(d.stage as string).charAt(0).toUpperCase()}${(d.stage as string).slice(1)} started`, description: `Starting ${d.stage} stage…`, data: null };
      case "search_queries_generated":
        return { stage: "search", title: "Search Queries", description: `Generated ${(d.queries as string[]).length} queries`, data: d.queries };
      case "sources_found":
        return { stage: "search", title: "Sources Found", description: `Discovered ${d.count} sources`, data: d.sources };
      case "evidence_extracted":
        return { stage: "search", title: "Evidence Extracted", description: `Extracted ${d.count} pieces of evidence`, data: d.samples };
      case "themes_identified":
        return { stage: "synthesis", title: "Themes Identified", description: `Identified ${d.count} themes`, data: d.themes };
      case "contradictions_identified":
        return { stage: "synthesis", title: "Contradictions", description: `Found ${d.count} contradictions`, data: d.contradictions };
      case "report_outline_generated":
        return { stage: "report", title: "Report Outline", description: `Planned ${(d.outline as string[]).length} sections`, data: d.outline };
      case "report_generated":
        return { stage: "report", title: "Report Generated", description: `${d.length} characters`, data: d.preview };
      case "evaluation_completed":
        return { stage: "evaluation", title: "Evaluation", description: `Coverage: ${((d.coverage as number) * 100).toFixed(0)}% | Usefulness: ${((d.usefulness as number) * 100).toFixed(0)}%`, data: d.reasoning };
      case "job_failed":
        return { stage: "evaluation", title: "Job Failed", description: d.error as string, data: null };
      default:
        return null;
    }
  }

  useEffect(() => {
    // Try SSE stream first, fall back to one-shot fetch
    const es = new EventSource(`${API_BASE}/api/research/${jobId}/events`);
    let receivedAny = false;

    es.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        receivedAny = true;
        setLoading(false);
        setAvailable(true);
        setLive(true);

        const step = mapEventToStep(event);
        if (step) {
          setSteps((prev) => [...prev, step]);
        }
        if (event.type === "job_completed" || event.type === "job_failed") {
          setLive(false);
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
      setLive(false);
      if (!receivedAny) {
        // Fall back to one-shot reasoning endpoint
        getReasoning(jobId)
          .then((res) => {
            setSteps(res.steps);
            setAvailable(res.available);
          })
          .catch(() => setAvailable(false))
          .finally(() => setLoading(false));
      }
    };

    return () => {
      es.close();
    };
  }, [jobId]);

  // Auto-scroll to bottom on new steps
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [steps.length]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
        Connecting to reasoning stream…
      </div>
    );
  }

  if (!available || steps.length === 0) {
    return (
      <p className="text-xs text-gray-500">
        Reasoning data not available for this job.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
        <span className={`inline-block h-2 w-2 rounded-full ${live ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
        {live ? "Live reasoning stream" : "Reasoning history"}
      </div>
      {steps.map((step, i) => (
        <StepCard key={i} step={step} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
