"use client";

import Link from "next/link";

interface StrengthCalloutProps {
  injuryTagCount: number;
}

export function StrengthCallout({ injuryTagCount }: StrengthCalloutProps) {
  const tailored = injuryTagCount > 0;
  const description = tailored
    ? "Exercises picked to support your injury history. Two short sessions a week cuts your injury risk."
    : "Running-specific strength staples. Two short sessions a week cuts your injury risk.";

  return (
    <Link
      href="/strength"
      className="block bg-white border border-gray-200 rounded-xl p-5 shadow-sm hover:shadow-md hover:border-blue-300 transition-all mb-6 group"
    >
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
          <svg
            className="w-5 h-5 text-blue-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
            />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-gray-900">
              Strength Playbook
            </h3>
            {tailored && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
                Tailored for you
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">{description}</p>
        </div>
        <span
          className="text-blue-600 text-sm font-medium group-hover:translate-x-0.5 transition-transform shrink-0 self-center"
          aria-hidden="true"
        >
          &rarr;
        </span>
      </div>
    </Link>
  );
}
