"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { jobs } from "@/lib/api";
import type { ProgressEvent, ProgressEventType } from "@/lib/types";

const EVENT_LABELS: Partial<Record<ProgressEventType, string>> = {
  job_started: "Starting plan generation...",
  planner_started: "Planner agent thinking...",
  planner_complete: "Planner finished iteration",
  validation_result: "Validating plan structure...",
  reviewer_started: "Reviewer agent scoring...",
  reviewer_complete: "Reviewer finished evaluation",
  retry: "Revising plan based on feedback...",
  token_budget: "Checking token budget...",
  job_complete: "Plan generation complete!",
  job_failed: "Plan generation failed",
};

interface PlanGenerationLoaderProps {
  jobId: string;
}

export function PlanGenerationLoader({ jobId }: PlanGenerationLoaderProps) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [status, setStatus] = useState<"running" | "complete" | "failed">(
    "running",
  );
  const router = useRouter();

  useEffect(() => {
    const source = jobs.stream(jobId);

    function handleEvent(e: MessageEvent) {
      const event = JSON.parse(e.data) as ProgressEvent;
      setEvents((prev) => [...prev, event]);

      if (event.event_type === "job_complete") {
        setStatus("complete");
        source.close();
        const planId = event.data.plan_id as string | undefined;
        if (planId) {
          setTimeout(() => router.push(`/plan/${planId}`), 1500);
        }
      } else if (event.event_type === "job_failed") {
        setStatus("failed");
        source.close();
      }
    }

    // Listen to all event types
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

    source.onerror = () => {
      setStatus("failed");
      source.close();
    };

    return () => {
      source.close();
    };
  }, [jobId, router]);

  const latestEvent = events[events.length - 1];
  const message =
    latestEvent
      ? EVENT_LABELS[latestEvent.event_type] ?? latestEvent.message
      : "Connecting...";

  return (
    <div className="flex flex-col items-center justify-center gap-6 py-16">
      {status === "running" && (
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full border-4 border-gray-200" />
          <div className="absolute inset-0 rounded-full border-4 border-blue-600 border-t-transparent animate-spin" />
        </div>
      )}

      {status === "complete" && (
        <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
          <svg
            className="w-8 h-8 text-green-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
        </div>
      )}

      {status === "failed" && (
        <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
          <svg
            className="w-8 h-8 text-red-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </div>
      )}

      <p className="text-lg font-medium text-gray-700">{message}</p>

      <div className="w-full max-w-md space-y-2">
        {events.map((event) => (
          <div
            key={event.sequence}
            className="flex items-center gap-2 text-sm text-gray-500"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
            {event.message}
          </div>
        ))}
      </div>
    </div>
  );
}
