"use client";

import type { EvaluationScores } from "@/lib/api";

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80
      ? "bg-green-500"
      : pct >= 60
      ? "bg-amber-500"
      : "bg-red-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-400">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-gray-700">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function ScoreCard({
  evaluation,
}: {
  evaluation: EvaluationScores;
}) {
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-300">Quality Scores</h3>
      <ScoreBar label="Coverage" value={evaluation.coverage} />
      <ScoreBar label="Faithfulness" value={evaluation.faithfulness} />
      <ScoreBar label="Usefulness" value={evaluation.usefulness} />
      <ScoreBar
        label="Hallucination risk"
        value={evaluation.hallucination_rate}
      />
    </div>
  );
}
