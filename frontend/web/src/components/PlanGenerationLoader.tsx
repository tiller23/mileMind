"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { jobs } from "@/lib/api";
import type { ProgressEvent, ProgressEventType } from "@/lib/types";

// Friendly labels instead of technical jargon
const EVENT_LABELS: Partial<Record<ProgressEventType, string>> = {
  job_started: "Getting everything ready...",
  planner_started: "Designing your training plan...",
  planner_complete: "Draft plan ready, checking quality...",
  validation_result: "Making sure everything looks right...",
  reviewer_started: "Reviewing for safety and balance...",
  reviewer_complete: "Review complete!",
  retry: "Fine-tuning a few things...",
  token_budget: "Almost there...",
  job_complete: "Your plan is ready!",
  job_failed: "Something went wrong",
};

// Map events to progress percentage (approximate)
const EVENT_PROGRESS: Partial<Record<ProgressEventType, number>> = {
  job_started: 5,
  planner_started: 15,
  planner_complete: 50,
  validation_result: 60,
  reviewer_started: 70,
  reviewer_complete: 85,
  retry: 40,
  token_budget: 90,
  job_complete: 100,
  job_failed: 100,
};

const TIPS = [
  "Most of your runs should feel easy enough to hold a conversation.",
  "Consistency beats intensity. Showing up matters more than any single workout.",
  "Rest days aren't lazy days. Your body gets stronger during recovery.",
  "A good warm-up can make a hard workout feel 10x better.",
  "Your easy pace should feel almost too slow. That's the point.",
  "Sleep is the most underrated performance enhancer.",
  "It takes about 10 days for a hard workout to fully pay off in fitness.",
  "Running with a friend can make easy miles fly by.",
  "Hydration matters more than you think, especially the day before a run.",
  "The hardest part of any run is usually the first mile.",
  "Cross-training can help you run better without adding impact.",
  "A training plan is a guide, not a contract. Listen to your body.",
  "Progressive overload works: small increases add up to big gains.",
  "Post-run stretching helps more than pre-run stretching for most runners.",
  "Your long run builds endurance that benefits every other distance.",
];

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

interface PlanGenerationLoaderProps {
  jobId: string;
}

export function PlanGenerationLoader({ jobId }: PlanGenerationLoaderProps) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [status, setStatus] = useState<"running" | "complete" | "failed">(
    "running",
  );
  const [tipIndex, setTipIndex] = useState(
    () => Math.floor(Math.random() * TIPS.length),
  );
  const [elapsed, setElapsed] = useState(0);
  const [progress, setProgress] = useState(2);
  const [message, setMessage] = useState("Getting everything ready...");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const router = useRouter();

  const handleComplete = useCallback(
    (planId?: string) => {
      setStatus("complete");
      setProgress(100);
      if (planId) {
        setTimeout(() => router.push(`/plan/${planId}`), 1500);
      }
    },
    [router],
  );

  // Poll job status as fallback when SSE drops
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    setMessage("Still working on your plan...");
    pollRef.current = setInterval(async () => {
      try {
        const job = await jobs.get(jobId);
        if (job.status === "complete") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          handleComplete(job.plan_id ?? undefined);
        } else if (job.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus("failed");
        }
      } catch {
        // keep polling
      }
    }, 5000);
  }, [jobId, handleComplete]);

  // Elapsed timer
  useEffect(() => {
    if (status !== "running") return;
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [status]);

  // Slowly advance progress between events so bar never feels stuck
  useEffect(() => {
    if (status !== "running") return;
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 92) return prev;
        return prev + 0.15;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [status]);

  // Rotate tips every 8 seconds
  useEffect(() => {
    if (status !== "running") return;
    const interval = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % TIPS.length);
    }, 8000);
    return () => clearInterval(interval);
  }, [status]);

  // SSE connection with polling fallback
  useEffect(() => {
    const source = jobs.stream(jobId);

    function handleEvent(e: MessageEvent) {
      let event: ProgressEvent;
      try {
        event = JSON.parse(e.data) as ProgressEvent;
      } catch {
        return;
      }
      setEvents((prev) => [...prev, event]);

      const label = EVENT_LABELS[event.event_type];
      if (label) setMessage(label);

      const eventProgress = EVENT_PROGRESS[event.event_type];
      if (eventProgress != null) {
        setProgress((prev) => Math.max(prev, eventProgress));
      }

      if (event.event_type === "job_complete") {
        source.close();
        const planId = event.data.plan_id as string | undefined;
        handleComplete(planId);
      } else if (event.event_type === "job_failed") {
        source.close();
        setStatus("failed");
      }
    }

    const eventTypes: ProgressEventType[] = [
      "job_started",
      "planner_started",
      "planner_complete",
      "validation_result",
      "reviewer_started",
      "reviewer_complete",
      "retry",
      "token_budget",
      "job_complete",
      "job_failed",
    ];
    for (const type of eventTypes) {
      source.addEventListener(type, handleEvent);
    }

    // On SSE error, fall back to polling instead of showing failure
    source.onerror = () => {
      source.close();
      startPolling();
    };

    return () => {
      source.close();
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobId, handleComplete, startPolling]);

  const barColor =
    status === "complete"
      ? "bg-green-500"
      : status === "failed"
        ? "bg-red-500"
        : "bg-blue-500";

  return (
    <div className="flex flex-col items-center justify-center gap-6 py-10">
      {/* Main message */}
      <p className="text-lg font-medium text-gray-800">{message}</p>

      {/* Progress bar */}
      <div className="w-full max-w-md">
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ease-out ${barColor}`}
            style={{ width: `${Math.min(progress, 100)}%` }}
            role="progressbar"
            aria-valuenow={Math.round(progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Plan generation progress"
          />
        </div>
      </div>

      {/* Time info */}
      {status === "running" && (
        <p className="text-sm text-gray-500">
          {formatElapsed(elapsed)} elapsed &middot; Hang tight — this takes a few minutes
        </p>
      )}

      {status === "complete" && (
        <p className="text-sm text-green-600 font-medium">
          Done in {formatElapsed(elapsed)}. Redirecting to your plan...
        </p>
      )}

      {status === "failed" && (
        <p className="text-sm text-red-600">
          Generation failed after {formatElapsed(elapsed)}. Please try again.
        </p>
      )}

      {/* Running tip */}
      {status === "running" && (
        <div className="max-w-sm text-center mt-4">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">
            While you wait...
          </p>
          <p className="text-sm text-gray-500 italic leading-relaxed">
            &ldquo;{TIPS[tipIndex]}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}
