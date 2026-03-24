"use client";

import Link from "next/link";
import { use } from "react";
import { Navbar } from "@/components/Navbar";
import { PlanCalendar } from "@/components/PlanCalendar";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { useArchivePlan, useAuthGuard, usePlan, useProfile } from "@/lib/hooks";

interface PlanPageProps {
  params: Promise<{ id: string }>;
}

export default function PlanPage({ params }: PlanPageProps) {
  const { isAuthenticated } = useAuthGuard();
  const { id } = use(params);
  const { data: plan, isLoading, error } = usePlan(id);
  const { data: profileData } = useProfile();
  const archivePlan = useArchivePlan();
  const units = profileData?.preferred_units ?? "metric";

  if (!isAuthenticated) return null;

  if (isLoading) {
    return (
      <>
        <Navbar />
        <main className="max-w-6xl mx-auto px-4 py-8">
          <div className="text-gray-400 text-center py-12">Loading plan...</div>
        </main>
      </>
    );
  }

  if (error || !plan) {
    return (
      <>
        <Navbar />
        <main className="max-w-6xl mx-auto px-4 py-8">
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

  const weeks = plan.plan_data?.weeks;
  const hasCalendar = weeks && weeks.length > 0;
  const planNotes = plan.plan_data?.notes;
  const supplementaryNotes = plan.plan_data?.supplementary_notes;

  return (
    <>
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-8 w-full">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Link
              href="/dashboard"
              className="text-sm text-blue-600 hover:underline mb-2 block"
            >
              &larr; Dashboard
            </Link>
            <h1 className="text-2xl font-bold">
              {plan.plan_data?.goal_event
                ? `${plan.plan_data.goal_event} Training Plan`
                : "Training Plan"}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              {hasCalendar ? `${weeks.length} weeks` : ""} &middot; Generated{" "}
              {new Date(plan.created_at).toLocaleDateString()}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href={`/plan/${id}/debug`}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors"
            >
              Debug View
            </Link>
            {plan.status === "active" && (
              <button
                onClick={() => archivePlan.mutate(id)}
                disabled={archivePlan.isPending}
                className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded-xl hover:bg-red-50 disabled:opacity-50 transition-colors"
              >
                Archive
              </button>
            )}
          </div>
        </div>

        {/* Status & Scores */}
        <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6 shadow-sm">
          <div className="flex items-center gap-4 mb-4">
            <StatusBadge
              variant={plan.approved ? "approved" : "unapproved"}
              label={plan.approved ? "Approved" : "Unapproved"}
              pill
            />
            <span className="text-sm text-gray-500">
              {plan.total_tokens.toLocaleString()} tokens &middot; $
              {plan.estimated_cost_usd.toFixed(2)}
            </span>
          </div>
          {plan.scores && <ScoreBadgeGroup scores={plan.scores} />}
        </div>

        {/* Plan notes */}
        {planNotes && (
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-5 mb-6 shadow-sm">
            <h2 className="text-sm font-semibold text-blue-800 mb-1">Plan Overview</h2>
            <p className="text-sm text-blue-700 leading-relaxed">{planNotes}</p>
          </div>
        )}

        {/* Calendar View */}
        {hasCalendar ? (
          <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold mb-5">Training Schedule</h2>
            <PlanCalendar weeks={weeks} units={units} />
          </div>
        ) : (
          <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm mb-6">
            <h2 className="text-lg font-semibold mb-4">Plan</h2>
            <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
              {plan.plan_data?.text ?? "No plan data available."}
            </div>
          </div>
        )}

        {/* Supplementary notes */}
        {supplementaryNotes && (
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Additional Notes</h2>
            <p className="text-sm text-gray-600 leading-relaxed">{supplementaryNotes}</p>
          </div>
        )}
      </main>
    </>
  );
}
