"use client";

import Link from "next/link";
import { use } from "react";
import { Navbar } from "@/components/Navbar";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { usePlanDebug } from "@/lib/hooks";

interface DebugPageProps {
  params: Promise<{ id: string }>;
}

export default function PlanDebugPage({ params }: DebugPageProps) {
  const { id } = use(params);
  const { data: debug, isLoading, error } = usePlanDebug(id);

  if (isLoading) {
    return (
      <>
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="text-gray-400 text-center py-12">Loading...</div>
        </main>
      </>
    );
  }

  if (error || !debug) {
    return (
      <>
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="text-red-600 text-center py-12">
            Debug info not found.
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <Link
          href={`/plan/${id}`}
          className="text-sm text-blue-600 hover:underline mb-4 block"
        >
          &larr; Back to plan
        </Link>
        <h1 className="text-2xl font-bold mb-2">Agent Decision Log</h1>
        <p className="text-sm text-gray-500 mb-6">
          {debug.total_tokens.toLocaleString()} tokens &middot; $
          {debug.estimated_cost_usd.toFixed(2)}
          {debug.approved ? " \u00B7 Approved" : " \u00B7 Not approved"}
        </p>

        {debug.scores && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-600 mb-2">
              Final Scores
            </h2>
            <ScoreBadgeGroup scores={debug.scores} />
          </div>
        )}

        <div className="space-y-4">
          {debug.decision_log.map((entry, i) => (
            <div
              key={i}
              className="bg-white border border-gray-200 rounded-lg p-5"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className="text-sm font-mono text-gray-400">
                  Iteration {entry.iteration}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${
                    entry.outcome === "approved"
                      ? "bg-green-100 text-green-800"
                      : entry.outcome === "rejected"
                        ? "bg-yellow-100 text-yellow-800"
                        : "bg-red-100 text-red-800"
                  }`}
                >
                  {entry.outcome}
                </span>
                <span className="text-xs text-gray-400">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>

              {entry.scores && <ScoreBadgeGroup scores={entry.scores} />}

              {entry.critique && (
                <div className="mt-3">
                  <div className="text-xs font-semibold text-gray-500 mb-1">
                    Critique
                  </div>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">
                    {entry.critique}
                  </p>
                </div>
              )}

              {entry.issues.length > 0 && (
                <div className="mt-3">
                  <div className="text-xs font-semibold text-gray-500 mb-1">
                    Issues
                  </div>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {entry.issues.map((issue, j) => (
                      <li key={j}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-3 flex gap-4 text-xs text-gray-400">
                <span>
                  Planner: {(entry.planner_input_tokens + entry.planner_output_tokens).toLocaleString()} tokens
                </span>
                <span>
                  Reviewer: {(entry.reviewer_input_tokens + entry.reviewer_output_tokens).toLocaleString()} tokens
                </span>
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
