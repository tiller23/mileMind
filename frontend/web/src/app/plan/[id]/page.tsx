"use client";

import Link from "next/link";
import { use } from "react";
import { Navbar } from "@/components/Navbar";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { useArchivePlan, usePlan } from "@/lib/hooks";

interface PlanPageProps {
  params: Promise<{ id: string }>;
}

export default function PlanPage({ params }: PlanPageProps) {
  const { id } = use(params);
  const { data: plan, isLoading, error } = usePlan(id);
  const archivePlan = useArchivePlan();

  if (isLoading) {
    return (
      <>
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="text-gray-400 text-center py-12">Loading plan...</div>
        </main>
      </>
    );
  }

  if (error || !plan) {
    return (
      <>
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="text-red-600 text-center py-12">
            Plan not found.{" "}
            <Link href="/dashboard" className="underline">
              Back to dashboard
            </Link>
          </div>
        </main>
      </>
    );
  }

  const rawText = plan.plan_data?.text;
  const planText = typeof rawText === "string" ? rawText : "";

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Link
              href="/dashboard"
              className="text-sm text-blue-600 hover:underline mb-2 block"
            >
              &larr; Dashboard
            </Link>
            <h1 className="text-2xl font-bold">Training Plan</h1>
            <p className="text-sm text-gray-500 mt-1">
              Generated {new Date(plan.created_at).toLocaleString()}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={`/plan/${id}/debug`}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Debug View
            </Link>
            {plan.status === "active" && (
              <button
                onClick={() => archivePlan.mutate(id)}
                disabled={archivePlan.isPending}
                className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-50"
              >
                Archive
              </button>
            )}
          </div>
        </div>

        {/* Status & Scores */}
        <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
          <div className="flex items-center gap-4 mb-4">
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${
                plan.approved
                  ? "bg-green-100 text-green-800"
                  : "bg-yellow-100 text-yellow-800"
              }`}
            >
              {plan.approved ? "Approved" : "Unapproved"}
            </span>
            <span className="text-sm text-gray-500">
              {plan.total_tokens.toLocaleString()} tokens &middot; $
              {plan.estimated_cost_usd.toFixed(2)}
            </span>
          </div>
          {plan.scores && <ScoreBadgeGroup scores={plan.scores} />}
        </div>

        {/* Plan Content */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Plan</h2>
          <div className="prose prose-sm max-w-none whitespace-pre-wrap font-mono text-sm leading-relaxed text-gray-700">
            {planText || "No plan text available."}
          </div>
        </div>
      </main>
    </>
  );
}
