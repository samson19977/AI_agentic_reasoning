"use client";

import { STATUS_LABELS, STATUS_COLORS, type JobStatus } from "@/lib/api";

const STEPS: JobStatus[] = [
  "searching",
  "synthesising",
  "reporting",
  "evaluating",
  "completed",
];

const STEP_INDEX: Record<string, number> = {};
STEPS.forEach((s, i) => {
  STEP_INDEX[s] = i;
});

export default function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-sm font-medium ${STATUS_COLORS[status]}`}
    >
      {!["completed", "failed"].includes(status) && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
        </span>
      )}
      {status === "completed" && <span>✓</span>}
      {status === "failed" && <span>✗</span>}
      {STATUS_LABELS[status]}
    </span>
  );
}

export function StatusStepper({ status }: { status: JobStatus }) {
  const currentIdx = STEP_INDEX[status] ?? -1;

  return (
    <div className="flex items-center gap-1 text-xs">
      {STEPS.map((step, i) => {
        const done = i < currentIdx || status === "completed";
        const active = i === currentIdx && status !== "completed" && status !== "failed";
        return (
          <div key={step} className="flex items-center gap-1">
            <div
              className={`h-2 w-2 rounded-full transition-colors ${
                done
                  ? "bg-green-500"
                  : active
                  ? "bg-blue-500 animate-pulse"
                  : "bg-gray-600"
              }`}
            />
            {i < STEPS.length - 1 && (
              <div
                className={`h-0.5 w-4 transition-colors ${
                  done ? "bg-green-500" : "bg-gray-700"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
