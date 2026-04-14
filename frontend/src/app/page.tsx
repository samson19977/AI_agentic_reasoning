"use client";

import { useState, useRef, useEffect, useCallback, FormEvent } from "react";
import { submitResearch, getJob, isTerminal, downloadPdf, type JobResult, type JobStatus } from "@/lib/api";
import StatusBadge, { StatusStepper } from "@/components/StatusBadge";
import ScoreCard from "@/components/ScoreCard";
import ReportView from "@/components/ReportView";
import ReasoningPanel from "@/components/ReasoningPanel";

// ── Chat message types ──────────────────────────────────────────────────────

interface UserMessage {
  role: "user";
  id: string;
  text: string;
}

interface AssistantMessage {
  role: "assistant";
  id: string;
  jobId: string;
  job: JobResult | null;
}

type ChatMessage = UserMessage | AssistantMessage;

// ── Download helper ─────────────────────────────────────────────────────────

function downloadReport(job: JobResult) {
  const slug = job.question
    .slice(0, 50)
    .replace(/[^a-zA-Z0-9 _-]/g, "")
    .trim()
    .replace(/\s+/g, "_");
  const filename = `${slug}_report.md`;
  const blob = new Blob([job.report], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Single assistant message with polling ────────────────────────────────────

function AssistantBubble({ msg, onJobUpdate }: {
  msg: AssistantMessage;
  onJobUpdate: (id: string, job: JobResult) => void;
}) {
  const [showReasoning, setShowReasoning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const job = msg.job;
  const isActive = job && !isTerminal(job.status);

  useEffect(() => {
    if (!isActive) return;

    const poll = async () => {
      try {
        const result = await getJob(msg.jobId);
        onJobUpdate(msg.id, result);
      } catch { /* ignore */ }
    };

    timerRef.current = setInterval(poll, 2000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [msg.jobId, msg.id, isActive, onJobUpdate]);

  if (!job) {
    return (
      <div className="flex gap-3">
        <div className="shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-sm">🔬</div>
        <div className="rounded-2xl rounded-tl-sm bg-gray-800 border border-gray-700 px-4 py-3 max-w-2xl">
          <p className="text-sm text-gray-400">Starting research…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-sm">🔬</div>
      <div className="flex-1 max-w-2xl space-y-3">
        {/* Status card */}
        <div className="rounded-2xl rounded-tl-sm bg-gray-800 border border-gray-700 px-4 py-3 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-gray-500 font-mono">{job.job_id}</span>
            <StatusBadge status={job.status} />
          </div>
          <StatusStepper status={job.status} />

          {job.status === "completed" && (
            <div className="flex gap-4 text-xs text-gray-400">
              <span>📚 {job.sources_count} sources</span>
              <span>🔗 {job.evidence_count} evidence</span>
              <span>🏷️ {job.themes_count} themes</span>
            </div>
          )}
        </div>

        {/* Error */}
        {job.status === "failed" && (
          <div className="rounded-2xl border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
            <p className="font-semibold">Research failed</p>
            <p className="mt-1 text-red-400">{job.error}</p>
          </div>
        )}

        {/* Evaluation scores */}
        {job.evaluation && <ScoreCard evaluation={job.evaluation} />}

        {/* Report */}
        {job.report && (
          <div className="rounded-2xl bg-gray-800 border border-gray-700 px-5 py-4">
            <ReportView markdown={job.report} />
          </div>
        )}

        {/* Action bar  */}
        {job.status === "completed" && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => downloadReport(job)}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-600 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 transition-colors"
            >
              ⬇ Download report
            </button>
            <button
              onClick={() => downloadPdf(job.job_id, job.question)}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-600 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 transition-colors"
            >
              📄 Download PDF
            </button>
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-600 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 transition-colors"
            >
              {showReasoning ? "🔼 Hide reasoning" : "🧠 Show reasoning steps"}
            </button>
          </div>
        )}

        {/* Reasoning panel */}
        {showReasoning && (
          <div className="rounded-2xl bg-gray-800/50 border border-gray-700 px-4 py-4">
            <ReasoningPanel jobId={job.job_id} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main chat page ──────────────────────────────────────────────────────────

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleJobUpdate = useCallback((msgId: string, job: JobResult) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId && m.role === "assistant" ? { ...m, job } : m
      )
    );
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || submitting) return;

    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    // Add user message
    const userMsg: UserMessage = { role: "user", id: userMsgId, text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSubmitting(true);

    try {
      const res = await submitResearch(text);

      // Add assistant message with job
      const assistantMsg: AssistantMessage = {
        role: "assistant",
        id: assistantMsgId,
        jobId: res.job_id,
        job: { ...res, report: "", evaluation: null, sources_count: 0, evidence_count: 0, themes_count: 0, error: "" },
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      // Show error as a failed assistant message
      const errMsg: AssistantMessage = {
        role: "assistant",
        id: assistantMsgId,
        jobId: "",
        job: {
          job_id: "",
          status: "failed",
          question: text,
          report: "",
          evaluation: null,
          sources_count: 0,
          evidence_count: 0,
          themes_count: 0,
          error: err instanceof Error ? err.message : "Failed to submit",
        },
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-57px)]">
      {/* ── Messages area ────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6 space-y-6">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full min-h-[40vh] text-center space-y-4">
              <div className="text-5xl">🔬</div>
              <h1 className="text-2xl font-bold text-gray-200">Research Assistant</h1>
              <p className="text-sm text-gray-400 max-w-md">
                Ask a research question and our AI agents will search the web,
                synthesise evidence, write a report, and evaluate its quality.
              </p>
              <div className="flex flex-wrap justify-center gap-2 mt-2">
                {[
                  "Trade-offs between CNNs and Vision Transformers",
                  "AI risks in higher education",
                  "Latest advances in quantum computing",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="rounded-full border border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) =>
            msg.role === "user" ? (
              <div key={msg.id} className="flex justify-end">
                <div className="rounded-2xl rounded-tr-sm bg-blue-600 px-4 py-2.5 max-w-xl">
                  <p className="text-sm text-white">{msg.text}</p>
                </div>
              </div>
            ) : (
              <AssistantBubble
                key={msg.id}
                msg={msg}
                onJobUpdate={handleJobUpdate}
              />
            )
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input bar ────────────────────────────────────────────────── */}
      <div className="border-t border-gray-800 bg-gray-900/80 backdrop-blur-sm">
        <form
          onSubmit={handleSubmit}
          className="mx-auto max-w-3xl flex items-center gap-2 px-4 py-3"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a research question…"
            disabled={submitting}
            className="flex-1 rounded-full border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={submitting || !input.trim()}
            className="rounded-full bg-blue-600 p-2.5 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Send"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
