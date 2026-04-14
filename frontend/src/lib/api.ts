export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Sent with every request if the env var is set. */
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return API_KEY
    ? { "X-API-Key": API_KEY, ...extra }
    : { ...extra };
}

// ── Types matching the FastAPI models ───────────────────────────────────────

export type JobStatus =
  | "pending"
  | "searching"
  | "synthesising"
  | "reporting"
  | "evaluating"
  | "completed"
  | "failed";

export interface EvaluationScores {
  coverage: number;
  faithfulness: number;
  hallucination_rate: number;
  usefulness: number;
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  question: string;
}

export interface JobResult {
  job_id: string;
  status: JobStatus;
  question: string;
  report: string;
  evaluation: EvaluationScores | null;
  sources_count: number;
  evidence_count: number;
  themes_count: number;
  error: string;
}

export interface ReasoningStep {
  stage: string;
  title: string;
  description: string;
  data: unknown;
}

export interface ReasoningResponse {
  job_id: string;
  status: JobStatus;
  available: boolean;
  steps: ReasoningStep[];
}

// ── API calls ───────────────────────────────────────────────────────────────

export async function submitResearch(question: string): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/api/research`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_BASE}/api/research/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getReasoning(jobId: string): Promise<ReasoningResponse> {
  const res = await fetch(`${API_BASE}/api/research/${jobId}/reasoning`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function listJobs(): Promise<JobResult[]> {
  const res = await fetch(`${API_BASE}/api/research`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/research/${jobId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
}

export async function clearAllJobs(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/research`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
}

export async function downloadPdf(jobId: string, question: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/research/${jobId}/pdf`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  const blob = await res.blob();
  const slug = question
    .slice(0, 50)
    .replace(/[^a-zA-Z0-9 _-]/g, "")
    .trim()
    .replace(/\s+/g, "_");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${slug}_report.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}

// ── Helpers ─────────────────────────────────────────────────────────────────

export function isTerminal(status: JobStatus): boolean {
  return status === "completed" || status === "failed";
}

export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "Pending",
  searching: "Searching the web…",
  synthesising: "Synthesising evidence…",
  reporting: "Writing report…",
  evaluating: "Evaluating quality…",
  completed: "Completed",
  failed: "Failed",
};

export const STATUS_COLORS: Record<JobStatus, string> = {
  pending: "text-gray-400",
  searching: "text-blue-400",
  synthesising: "text-purple-400",
  reporting: "text-amber-400",
  evaluating: "text-cyan-400",
  completed: "text-green-400",
  failed: "text-red-400",
};
