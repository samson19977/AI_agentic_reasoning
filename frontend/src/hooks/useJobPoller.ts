"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getJob, isTerminal, type JobResult } from "@/lib/api";

/**
 * Poll a job until it reaches a terminal state (completed / failed).
 * Returns the latest job result and a loading flag.
 */
export function useJobPoller(jobId: string | null, intervalMs = 2000) {
  const [job, setJob] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Reset when jobId changes
  useEffect(() => {
    setJob(null);
    setError(null);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const result = await getJob(jobId);
        if (cancelled) return;
        setJob(result);
        if (isTerminal(result.status)) {
          stop();
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Polling failed");
        stop();
      }
    };

    // Initial fetch immediately
    poll();
    timerRef.current = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId, intervalMs, stop]);

  return { job, error, stop };
}

/**
 * Track a callback whenever a specific job ID's result changes.
 * Used by the chat to update messages in-place.
 */
export function useJobUpdater(
  jobId: string | null,
  onUpdate: (job: JobResult) => void,
  intervalMs = 2000,
) {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const result = await getJob(jobId);
        if (cancelled) return;
        onUpdateRef.current(result);
        if (isTerminal(result.status)) stop();
      } catch {
        if (!cancelled) stop();
      }
    };

    poll();
    timerRef.current = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId, intervalMs, stop]);

  return { stop };
}
