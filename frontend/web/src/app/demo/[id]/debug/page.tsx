"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useDemoPlanDebug } from "@/lib/hooks";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { Logo } from "@/components/Logo";

export default function DemoPlanDebugPage() {
  const params = useParams();
  const planId = params.id as string;
  const { data: debug, isLoading, error } = useDemoPlanDebug(planId);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (error || !debug) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Debug info not found</h1>
          <Link href="/demo" className="text-indigo-600 hover:text-indigo-700">
            &larr; Back to demo plans
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2">
              <Logo size={28} />
              <span className="text-lg font-semibold text-gray-900">MileMind</span>
            </Link>
            <span className="text-gray-300">|</span>
            <Link href="/demo" className="text-sm text-gray-500 hover:text-gray-700">
              Demo Plans
            </Link>
          </div>
          <Link
            href="/login"
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
          >
            Sign in &rarr;
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Demo banner */}
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3 mb-6">
          <p className="text-sm text-indigo-700">
            This is the AI transparency view for a demo plan.{" "}
            <Link href={`/demo/${planId}`} className="font-medium underline">
              View the training calendar
            </Link>
          </p>
        </div>

        <Link
          href={`/demo/${planId}`}
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
              className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className="text-sm font-mono text-gray-400">
                  Iteration {entry.iteration}
                </span>
                <StatusBadge variant={entry.outcome} />
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
    </div>
  );
}
