"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { StravaConnect } from "@/components/StravaConnect";
import { useAuthGuard, useProfile, useUpsertProfile } from "@/lib/hooks";
import type { InjuryTag, ProfileUpdate } from "@/lib/types";
import { INJURY_TAG_LABEL } from "@/lib/labels";
import { KM_TO_MILES, MILES_TO_KM } from "@/lib/units";
import { GOAL_OPTIONS, RISK_OPTIONS } from "@/lib/enums";

const DURATION_OPTIONS: { value: number; label: string }[] = [
  { value: 8, label: "8 weeks" },
  { value: 10, label: "10 weeks" },
  { value: 12, label: "12 weeks" },
  { value: 16, label: "16 weeks" },
  { value: 20, label: "20 weeks" },
  { value: 24, label: "24 weeks" },
];

const DEFAULTS: ProfileUpdate = {
  name: "",
  age: 30,
  vo2max: null,
  vdot: null,
  weekly_mileage_base: 20,
  hr_max: null,
  hr_rest: null,
  injury_history: "",
  risk_tolerance: "moderate",
  max_weekly_increase_pct: 0.1,
  goal_distance: "general_fitness",
  goal_time_minutes: null,
  training_days_per_week: 4,
  long_run_cap_pct: 0.3,
  preferred_units: "imperial",
  plan_duration_weeks: 12,
  injury_tags: [],
  current_acute_injury: false,
  current_injury_description: "",
};

const INJURY_TAG_OPTIONS: { value: InjuryTag; label: string }[] = (
  Object.entries(INJURY_TAG_LABEL) as [InjuryTag, string][]
).map(([value, label]) => ({ value, label }));

const inputClass =
  "w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors";

export default function OnboardingPage() {
  const { isAuthenticated } = useAuthGuard();
  const router = useRouter();
  const { data: existing } = useProfile();
  const upsert = useUpsertProfile();
  const [form, setForm] = useState<ProfileUpdate>(DEFAULTS);

  useEffect(() => {
    if (existing) {
      // DB stores km — convert to miles for display if imperial
      const displayMileage = existing.preferred_units === "imperial"
        ? Math.round(existing.weekly_mileage_base * KM_TO_MILES * 10) / 10
        : existing.weekly_mileage_base;
      setForm({
        ...existing,
        weekly_mileage_base: displayMileage,
        // Guard against legacy rows missing the newer columns.
        injury_tags: existing.injury_tags ?? [],
        current_acute_injury: existing.current_acute_injury ?? false,
        current_injury_description: existing.current_injury_description ?? "",
      });
    }
  }, [existing]);

  if (!isAuthenticated) return null;

  function update<K extends keyof ProfileUpdate>(
    key: K,
    value: ProfileUpdate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Convert miles → km for storage if imperial
    const payload = { ...form };
    if (payload.preferred_units === "imperial") {
      payload.weekly_mileage_base = Math.round(payload.weekly_mileage_base * MILES_TO_KM * 10) / 10;
    }
    await upsert.mutateAsync(payload);
    router.push("/dashboard");
  }

  return (
    <>
      <Navbar />
      <main className="max-w-xl mx-auto px-4 py-8 w-full">
        <h1 className="text-2xl font-bold mb-2">
          {existing ? "Update Profile" : "Your Running Profile"}
        </h1>
        <p className="text-sm text-gray-500 mb-8">
          {existing
            ? "Update your running details anytime."
            : "Help us understand your running so we can build the right plan."}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm divide-y divide-gray-100">
            {/* Section: About You */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                About You
              </h2>

              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                  Name
                </label>
                <input
                  id="name"
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                  className={inputClass}
                />
              </div>

              <div>
                <span id="units-label" className="block text-sm font-medium text-gray-700 mb-2">
                  Preferred units
                </span>
                <div
                  className="flex rounded-xl border border-gray-300 overflow-hidden"
                  role="radiogroup"
                  aria-labelledby="units-label"
                >
                  {(["imperial", "metric"] as const).map((unit) => (
                    <button
                      key={unit}
                      type="button"
                      role="radio"
                      aria-checked={form.preferred_units === unit}
                      onClick={() => update("preferred_units", unit)}
                      className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                        form.preferred_units === unit
                          ? "bg-blue-600 text-white"
                          : "bg-white text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {unit === "imperial" ? "Miles" : "Kilometers"}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="age" className="block text-sm font-medium text-gray-700 mb-1">
                  Age
                </label>
                <input
                  id="age"
                  type="number"
                  required
                  min={10}
                  max={100}
                  value={form.age || ""}
                  onChange={(e) =>
                    update("age", e.target.value ? Number(e.target.value) : 0)
                  }
                  placeholder="e.g., 30"
                  className={inputClass}
                />
              </div>
            </div>

            {/* Section: Running Background */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                Running Background
              </h2>

              <div>
                <label htmlFor="goal_distance" className="block text-sm font-medium text-gray-700 mb-1">
                  What&apos;s your running goal?
                </label>
                <select
                  id="goal_distance"
                  value={form.goal_distance}
                  onChange={(e) => update("goal_distance", e.target.value)}
                  className={inputClass}
                >
                  {GOAL_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {form.goal_distance !== "general_fitness" && (
                <div>
                  <label htmlFor="goal_time" className="block text-sm font-medium text-gray-700 mb-1">
                    Target time (minutes, optional)
                  </label>
                  <input
                    id="goal_time"
                    type="number"
                    min={1}
                    value={form.goal_time_minutes ?? ""}
                    onChange={(e) =>
                      update(
                        "goal_time_minutes",
                        e.target.value ? Number(e.target.value) : null,
                      )
                    }
                    placeholder="e.g., 25 for a 25-minute 5K"
                    className={inputClass}
                  />
                </div>
              )}

              <div>
                <label htmlFor="weekly_mileage" className="block text-sm font-medium text-gray-700 mb-1">
                  Current weekly mileage ({form.preferred_units === "imperial" ? "miles" : "km"})
                </label>
                <input
                  id="weekly_mileage"
                  type="number"
                  required
                  min={0}
                  step={0.1}
                  value={form.weekly_mileage_base || ""}
                  onChange={(e) =>
                    update("weekly_mileage_base", e.target.value ? Number(e.target.value) : 0)
                  }
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="training_days" className="block text-sm font-medium text-gray-700 mb-1">
                  How many days per week do you want to train?
                </label>
                <input
                  id="training_days"
                  type="number"
                  required
                  min={3}
                  max={7}
                  value={form.training_days_per_week || ""}
                  onChange={(e) =>
                    update("training_days_per_week", e.target.value ? Number(e.target.value) : 0)
                  }
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="plan_duration" className="block text-sm font-medium text-gray-700 mb-1">
                  Plan duration
                </label>
                <select
                  id="plan_duration"
                  value={form.plan_duration_weeks}
                  onChange={(e) => update("plan_duration_weeks", Number(e.target.value))}
                  className={inputClass}
                >
                  {DURATION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Section: Preferences */}
            <div className="p-6 space-y-5">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                Preferences
              </h2>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Training approach
                </label>
                <div className="space-y-2">
                  {RISK_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`flex items-start gap-3 p-3 border rounded-xl cursor-pointer transition-all ${
                        form.risk_tolerance === opt.value
                          ? "border-blue-500 bg-blue-50 shadow-sm"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <input
                        type="radio"
                        name="risk_tolerance"
                        value={opt.value}
                        checked={form.risk_tolerance === opt.value}
                        onChange={() => update("risk_tolerance", opt.value)}
                        className="mt-0.5"
                      />
                      <div>
                        <div className="font-medium text-sm">{opt.label}</div>
                        <div className="text-xs text-gray-500">{opt.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="injury_history" className="block text-sm font-medium text-gray-700 mb-1">
                  Injury History (optional)
                </label>
                <textarea
                  id="injury_history"
                  value={form.injury_history}
                  onChange={(e) => update("injury_history", e.target.value)}
                  maxLength={500}
                  rows={3}
                  placeholder="Anything we should know about — past or current"
                  className={inputClass}
                />
              </div>

              <div>
                <span className="block text-sm font-medium text-gray-700 mb-2">
                  Injury tags (select any that apply)
                </span>
                <div className="flex flex-wrap gap-2">
                  {INJURY_TAG_OPTIONS.map((opt) => {
                    const selected = form.injury_tags.includes(opt.value);
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => {
                          const next = selected
                            ? form.injury_tags.filter((t) => t !== opt.value)
                            : [...form.injury_tags, opt.value];
                          update("injury_tags", next);
                        }}
                        className={
                          "px-3 py-1.5 rounded-full border text-sm transition-colors " +
                          (selected
                            ? "bg-blue-600 text-white border-blue-600"
                            : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50")
                        }
                        aria-pressed={selected}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Used by the strength playbook to tailor exercises to your history.
                </p>
              </div>

              <div>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.current_acute_injury}
                    onChange={(e) =>
                      update("current_acute_injury", e.target.checked)
                    }
                    className="mt-1"
                  />
                  <span className="text-sm text-gray-700">
                    I have a <strong>current</strong> injury right now (not just
                    past history). We&apos;ll recommend seeing a PT before
                    starting new strength work.
                  </span>
                </label>
                {form.current_acute_injury && (
                  <textarea
                    aria-label="Describe your current injury"
                    value={form.current_injury_description}
                    onChange={(e) =>
                      update("current_injury_description", e.target.value)
                    }
                    maxLength={500}
                    rows={2}
                    placeholder="Briefly, what's going on? (optional)"
                    className={inputClass + " mt-2"}
                  />
                )}
              </div>

              <div>
                <label htmlFor="vdot" className="block text-sm font-medium text-gray-700 mb-1">
                  VDOT (optional)
                </label>
                <input
                  id="vdot"
                  type="number"
                  min={15}
                  max={85}
                  step={0.1}
                  value={form.vdot ?? ""}
                  onChange={(e) =>
                    update("vdot", e.target.value ? Number(e.target.value) : null)
                  }
                  placeholder="Leave blank if unsure"
                  className={inputClass}
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={upsert.isPending}
            className="w-full mt-6 px-4 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {upsert.isPending
              ? "Saving..."
              : existing
                ? "Update Profile"
                : "Save & Continue"}
          </button>

          {upsert.isError && (
            <p className="text-red-600 text-sm text-center mt-3">
              {upsert.error instanceof Error
                ? upsert.error.message
                : "Failed to save profile"}
            </p>
          )}
        </form>

        {/* Connected Services */}
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Connected Services
          </h2>
          <StravaConnect
            units={form.preferred_units}
            onMileageSuggestion={(km) => {
              const display =
                form.preferred_units === "imperial"
                  ? Math.round(km * KM_TO_MILES * 10) / 10
                  : km;
              update("weekly_mileage_base", display);
            }}
          />
        </div>
      </main>
    </>
  );
}
