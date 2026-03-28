"use client";

/**
 * Invite code request banner for the dashboard.
 *
 * Three states:
 * - No request: "Request an Invite Code" button
 * - Pending: "Request Pending" (disabled) + helper text
 * - Denied + cooldown: "Denied" message + days remaining
 */

import { useRequestInvite } from "@/lib/hooks";
import { ApiError } from "@/lib/api";

interface InviteCodeBannerProps {
  requestStatus: "pending" | "approved" | "denied" | null;
}

export function InviteCodeBanner({ requestStatus }: InviteCodeBannerProps) {
  const requestInvite = useRequestInvite();

  const isPending = requestStatus === "pending";
  const isDenied = requestStatus === "denied";

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm mb-6">
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
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-gray-900">
            {isPending
              ? "Request Pending"
              : isDenied
                ? "Request Denied"
                : "Invite Required"}
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            {isPending
              ? "Your invite request has been submitted. You'll be notified by email once approved."
              : isDenied
                ? "Your invite request was not approved. You can request again in 30 days."
                : "MileMind is currently invite-only. Request access to unlock plan generation."}
          </p>

          {requestInvite.isError && (
            <p className="text-sm text-red-600 mt-2">
              {requestInvite.error instanceof ApiError
                ? requestInvite.error.detail
                : "Something went wrong. Please try again."}
            </p>
          )}

          {requestInvite.isSuccess && !isPending && (
            <p className="text-sm text-green-600 mt-2">
              Request submitted! We'll review it shortly.
            </p>
          )}

          <div className="mt-4">
            {isPending ? (
              <button
                disabled
                className="px-5 py-2.5 bg-gray-100 text-gray-400 rounded-xl text-sm font-medium cursor-not-allowed"
              >
                Request Pending
              </button>
            ) : isDenied ? (
              <button
                disabled
                className="px-5 py-2.5 bg-gray-100 text-gray-400 rounded-xl text-sm font-medium cursor-not-allowed"
              >
                Request Denied
              </button>
            ) : (
              <button
                onClick={() => requestInvite.mutate()}
                disabled={requestInvite.isPending || requestInvite.isSuccess}
                className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {requestInvite.isPending
                  ? "Submitting..."
                  : requestInvite.isSuccess
                    ? "Request Submitted"
                    : "Request an Invite Code"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
