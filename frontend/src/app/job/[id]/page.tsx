"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useJobPoller } from "@/hooks/useJobPoller";
import StatusBadge, { StatusStepper } from "@/components/StatusBadge";
import ScoreCard from "@/components/ScoreCard";
import ReportView from "@/components/ReportView";
import ReasoningPanel from "@/components/ReasoningPanel";
import type { JobResult } from "@/lib/api";
import { downloadPdf } from "@/lib/api";

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

export default function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { job, error } = useJobPoller(id);
  const [showReasoning, setShowReasoning] = useState(false);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-sm text-red-400">{error}</p>
        <Link href="/history" className="mt-4 inline-block text-sm text-blue-400">
          ← Back to history
        </Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-sm text-gray-400">Loading…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-6">
      <Link
        href="/history"
        className="inline-block text-sm text-gray-400 hover:text-gray-200 transition-colors"
      >
        ← Back to history
      </Link>

      {/* Header card */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-5 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <p className="text-sm text-gray-400 font-mono">Job {job.job_id}</p>
            <h1 className="text-lg font-semibold text-gray-100">
              {job.question}
            </h1>
          </div>
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
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-4 text-sm text-red-300">
          <p className="font-semibold">Research failed</p>
          <p className="mt-1 text-red-400">{job.error}</p>
        </div>
      )}

      {/* Evaluation scores */}
      {job.evaluation && <ScoreCard evaluation={job.evaluation} />}

      {/* Action bar */}
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
        <div className="rounded-lg bg-gray-800/50 border border-gray-700 p-4">
          <ReasoningPanel jobId={job.job_id} />
        </div>
      )}

      {/* Report */}
      {job.report && (
        <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
          <ReportView markdown={job.report} />
        </div>
      )}
    </div>
  );
}
