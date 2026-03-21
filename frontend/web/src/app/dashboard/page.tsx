"use client";

import Link from "next/link";
import { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { PlanGenerationLoader } from "@/components/PlanGenerationLoader";
import { ScoreBadgeGroup } from "@/components/ScoreBadge";
import { useGeneratePlan, usePlans, useProfile } from "@/lib/hooks";

export default function DashboardPage() {
  const { data: profileData, isLoading: profileLoading, error: profileError } = useProfile();
  const { data: plansData, isLoading: plansLoading } = usePlans();
  const generatePlan = useGeneratePlan();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const needsOnboarding = profileError && "status" in profileError && profileError.status === 404;

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
              className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {generatePlan.isPending ? "Starting..." : "Generate Plan"}
            </button>
          )}
        </div>

        {needsOnboarding && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
            <h2 className="text-lg font-semibold text-yellow-800 mb-2">
              Complete Your Profile
            </h2>
            <p className="text-yellow-700 mb-4">
              We need a few details about your running background to generate
              your training plan.
            </p>
            <Link
              href="/onboarding"
              className="inline-block px-4 py-2 bg-yellow-600 text-white rounded-lg font-medium hover:bg-yellow-700"
            >
              Start Onboarding
            </Link>
          </div>
        )}

        {generatePlan.isError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800">
              {generatePlan.error instanceof Error
                ? generatePlan.error.message
                : "Failed to start plan generation"}
            </p>
          </div>
        )}

        {activeJobId && (
          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
            <PlanGenerationLoader jobId={activeJobId} />
          </div>
        )}

        {profileLoading || plansLoading ? (
          <div className="text-gray-400 text-center py-12">Loading...</div>
        ) : (
          <div className="space-y-4">
            {plansData && plansData.length > 0 ? (
              plansData.map((plan) => (
                <Link
                  key={plan.id}
                  href={`/plan/${plan.id}`}
                  className="block bg-white border border-gray-200 rounded-lg p-5 hover:border-blue-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          plan.approved
                            ? "bg-green-100 text-green-800"
                            : "bg-yellow-100 text-yellow-800"
                        }`}
                      >
                        {plan.approved ? "Approved" : "Unapproved"}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          plan.status === "active"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {plan.status}
                      </span>
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
                <div className="text-center py-12 text-gray-400">
                  No plans yet. Click &quot;Generate Plan&quot; to create your
                  first training plan.
                </div>
              )
            )}
          </div>
        )}
      </main>
    </>
  );
}
