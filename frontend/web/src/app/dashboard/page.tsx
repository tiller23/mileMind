"use client";

import Link from "next/link";
import { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { PlanGenerationLoader } from "@/components/PlanGenerationLoader";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuthGuard, useGeneratePlan, usePlans, useProfile } from "@/lib/hooks";

function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm animate-pulse">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="h-5 w-20 bg-gray-200 rounded" />
          <div className="h-5 w-16 bg-gray-200 rounded" />
        </div>
        <div className="h-4 w-24 bg-gray-100 rounded" />
      </div>
      <div className="flex gap-2">
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
        <div className="h-6 w-24 bg-gray-100 rounded-full" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { isAuthenticated } = useAuthGuard();
  const { data: profileData, isLoading: profileLoading } = useProfile();
  const { data: plansData, isLoading: plansLoading } = usePlans();
  const generatePlan = useGeneratePlan();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const needsOnboarding = !profileLoading && profileData === null;

  if (!isAuthenticated) return null;

  async function handleGenerate() {
    const result = await generatePlan.mutateAsync({ change_type: "full" });
    setActiveJobId(result.job_id);
  }

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          {profileData && !activeJobId && (
            <button
              onClick={handleGenerate}
              disabled={generatePlan.isPending}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
            >
              {generatePlan.isPending ? "Starting..." : "Generate Plan"}
            </button>
          )}
        </div>

        {needsOnboarding && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-8 text-center shadow-sm">
            <div className="mx-auto w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center mb-4 text-2xl">
              👟
            </div>
            <h2 className="text-lg font-semibold text-amber-800 mb-2">
              Complete Your Profile
            </h2>
            <p className="text-amber-700 mb-5 text-sm">
              Tell us about your running so we can build a plan that fits.
            </p>
            <Link
              href="/onboarding"
              className="inline-block px-5 py-2.5 bg-amber-600 text-white rounded-xl font-medium hover:bg-amber-700 transition-colors"
            >
              Get Started
            </Link>
          </div>
        )}

        {generatePlan.isError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 shadow-sm">
            <p className="text-red-800 text-sm">
              {generatePlan.error instanceof Error
                ? generatePlan.error.message
                : "Failed to start plan generation"}
            </p>
          </div>
        )}

        {activeJobId && (
          <div className="bg-white border border-gray-200 rounded-xl p-6 mb-6 shadow-sm">
            <PlanGenerationLoader jobId={activeJobId} />
          </div>
        )}

        {profileLoading || plansLoading ? (
          <div className="space-y-4">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <div className="space-y-4">
            {plansData && plansData.length > 0 ? (
              plansData.map((plan) => (
                <Link
                  key={plan.id}
                  href={`/plan/${plan.id}`}
                  className="block bg-white border border-gray-200 rounded-xl p-5 shadow-sm hover:shadow-md hover:border-blue-300 transition-all"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <StatusBadge variant={plan.approved ? "approved" : "unapproved"} label={plan.approved ? "Approved" : "Unapproved"} />
                      <StatusBadge variant={plan.status === "active" ? "active" : "archived"} label={plan.status} />
                    </div>
                    <span className="text-sm text-gray-400">
                      {new Date(plan.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {plan.scores && <ScoreBadgeGroup scores={plan.scores} />}
                </Link>
              ))
            ) : (
              !needsOnboarding &&
              profileData &&
              !activeJobId && (
                <div className="text-center py-16">
                  <div className="mx-auto w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mb-4 text-2xl">
                    🏃
                  </div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-1">
                    Ready to start training
                  </h3>
                  <p className="text-sm text-gray-500 mb-6">
                    Generate your first AI-powered training plan.
                  </p>
                  <button
                    onClick={handleGenerate}
                    disabled={generatePlan.isPending}
                    className="px-6 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                  >
                    Generate My Plan
                  </button>
                </div>
              )
            )}
          </div>
        )}
      </main>
    </>
  );
}
