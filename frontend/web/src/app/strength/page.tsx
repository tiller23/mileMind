"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import {
  useAuthGuard,
  useProfile,
  useStrengthPlaybook,
} from "@/lib/hooks";

import type { StrengthExercise } from "@/lib/types";

const DIFFICULTY_LABEL: Record<StrengthExercise["difficulty"], string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

const ACUTE_GATE_STORAGE_KEY = "mm.strength.acuteGateAcknowledged";

export default function StrengthPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuthGuard();
  const { data: profile, isLoading: profileLoading } = useProfile();
  const { data, isLoading, error } = useStrengthPlaybook();
  const [acuteAcknowledged, setAcuteAcknowledged] = useState(false);

  useEffect(() => {
    if (!profile) return;
    const key = `${ACUTE_GATE_STORAGE_KEY}:${profile.id}`;
    // Clear stale acknowledgement when the gate is no longer active so a
    // newly-flagged injury re-shows the PT warning.
    if (!data?.acute_injury_gate.active) {
      window.sessionStorage.removeItem(key);
      setAcuteAcknowledged(false);
      return;
    }
    setAcuteAcknowledged(window.sessionStorage.getItem(key) === "1");
  }, [profile, data?.acute_injury_gate.active]);

  if (!isAuthenticated) return null;

  if (!profileLoading && !profile) {
    return (
      <>
        <Navbar />
        <main className="max-w-3xl mx-auto px-4 py-12 text-center">
          <h1 className="text-2xl font-bold mb-2">Strength Playbook</h1>
          <p className="text-gray-600 mb-6">
            Complete onboarding so we can tailor exercises to your running.
          </p>
          <Link
            href="/onboarding"
            className="inline-block px-4 py-2 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700"
          >
            Go to onboarding
          </Link>
        </main>
      </>
    );
  }

  if (authLoading || isLoading || profileLoading) {
    return (
      <>
        <Navbar />
        <main className="max-w-3xl mx-auto px-4 py-12 text-center text-gray-500">
          Loading your playbook…
        </main>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Navbar />
        <main className="max-w-3xl mx-auto px-4 py-12 text-center text-red-600">
          Couldn&apos;t load your playbook. Try refreshing in a bit.
        </main>
      </>
    );
  }

  const gateVisible = data.acute_injury_gate.active && !acuteAcknowledged;

  function acknowledgeGate() {
    if (typeof window === "undefined" || !profile) return;
    const key = `${ACUTE_GATE_STORAGE_KEY}:${profile.id}`;
    window.sessionStorage.setItem(key, "1");
    setAcuteAcknowledged(true);
  }

  const hasBlocks = data.blocks.length > 0;

  return (
    <>
      <Navbar />
      <main className="max-w-3xl mx-auto px-4 py-8 w-full">
        <header className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Strength Playbook</h1>
          <p className="text-gray-600">
            Running-specific strength tailored to your history. Pick one or
            two exercises per block based on what you have equipment for.
            Aim for 2 short sessions a week.
          </p>
        </header>

        {gateVisible && (
          <div
            role="alert"
            className="mb-6 border border-amber-300 bg-amber-50 rounded-xl p-4"
          >
            <h2 className="font-semibold text-amber-900 mb-1">
              You flagged a current injury
            </h2>
            <p className="text-sm text-amber-900 mb-3">
              Before starting new strength work,{" "}
              <strong>we strongly recommend seeing a physical therapist</strong>
              . What&apos;s safe depends on your specific diagnosis, and we
              can&apos;t assess that from here.
            </p>
            {data.acute_injury_gate.description.trim() && (
              <p className="text-sm text-amber-900 italic mb-3">
                Your note: &ldquo;{data.acute_injury_gate.description.trim()}&rdquo;
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={acknowledgeGate}
                className="text-sm px-3 py-1.5 rounded-lg bg-amber-900 text-white font-medium hover:bg-amber-800"
              >
                I understand
              </button>
              <Link
                href="/onboarding"
                className="text-sm px-3 py-1.5 rounded-lg border border-amber-900 text-amber-900 font-medium hover:bg-amber-100"
              >
                Update injury status
              </Link>
            </div>
          </div>
        )}

        {!gateVisible && !hasBlocks && (
          <div className="border border-gray-200 rounded-xl p-6 text-sm text-gray-600 bg-gray-50">
            <p className="mb-3">
              No playbook is shown while you have an active injury flagged.
              Once you&apos;re cleared, uncheck &ldquo;current injury&rdquo; in
              your profile and the playbook will return.
            </p>
            <Link
              href="/onboarding"
              className="inline-block text-sm px-3 py-1.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
            >
              Update injury status
            </Link>
          </div>
        )}

        {!gateVisible && hasBlocks && (
          <div className="space-y-8">
            {data.blocks.map((block) => (
              <section
                key={block.block_id}
                className="border border-gray-200 rounded-2xl p-5 bg-white"
              >
                <div className="mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <h2 className="text-xl font-semibold">{block.title}</h2>
                    {block.matched_injury_tags.length > 0 && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                        Tailored for: {block.matched_injury_tags.join(", ")}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 leading-relaxed">
                    {block.rationale}
                  </p>
                </div>
                <ul className="grid sm:grid-cols-2 gap-3">
                  {block.exercises.map((ex) => (
                    <li
                      key={ex.id}
                      className="border border-gray-200 rounded-xl p-3 hover:border-blue-400 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <a
                          href={`https://www.google.com/search?q=${encodeURIComponent(ex.search_query)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-gray-900 hover:text-blue-700"
                        >
                          {ex.name}
                        </a>
                        <span className="text-xs text-gray-500 whitespace-nowrap">
                          {DIFFICULTY_LABEL[ex.difficulty] ?? ex.difficulty}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {ex.equipment.map((eq) => (
                          <span
                            key={eq}
                            className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-700"
                          >
                            {eq}
                          </span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}

        <footer className="mt-10 text-xs text-gray-500 text-center">
          {data.catalog_version && (
            <>Catalog version {data.catalog_version}. </>
          )}
          These are general running-strength staples, not medical advice.
        </footer>
      </main>
    </>
  );
}
