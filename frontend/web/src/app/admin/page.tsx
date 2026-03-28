"use client";

/**
 * Admin page for managing invite requests.
 *
 * Displays pending/approved/denied requests with approve/deny actions.
 * Requires admin role — redirects non-admins to dashboard.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "@/components/Navbar";
import {
  useUser,
  useAdminInviteRequests,
  useApproveInviteRequest,
  useDenyInviteRequest,
} from "@/lib/hooks";

type StatusFilter = "pending" | "approved" | "denied" | undefined;

export default function AdminPage() {
  const router = useRouter();
  const { data: user, isLoading: userLoading } = useUser();
  const [filter, setFilter] = useState<StatusFilter>("pending");
  const { data: requests, isLoading } = useAdminInviteRequests(filter);
  const approve = useApproveInviteRequest();
  const deny = useDenyInviteRequest();

  // Redirect non-admins and unauthenticated users
  useEffect(() => {
    if (!userLoading && !user) {
      router.push("/login");
    } else if (!userLoading && user && user.role !== "admin") {
      router.push("/dashboard");
    }
  }, [userLoading, user, router]);

  if (userLoading) {
    return (
      <>
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="animate-pulse h-8 w-48 bg-gray-200 rounded mb-6" />
        </main>
      </>
    );
  }

  const filterTabs: { label: string; value: StatusFilter }[] = [
    { label: "Pending", value: "pending" },
    { label: "Approved", value: "approved" },
    { label: "Denied", value: "denied" },
    { label: "All", value: undefined },
  ];

  return (
    <>
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8 w-full">
        <h1 className="text-2xl font-bold mb-1">Admin</h1>
        <p className="text-sm text-gray-500 mb-6">Invite request management</p>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
          {filterTabs.map((tab) => (
            <button
              key={tab.label}
              onClick={() => setFilter(tab.value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                filter === tab.value
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.label}
              {tab.value === "pending" && requests && filter === "pending" && (
                <span className="ml-1.5 px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                  {requests.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Request list */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse"
              >
                <div className="h-4 w-48 bg-gray-200 rounded mb-2" />
                <div className="h-3 w-32 bg-gray-100 rounded" />
              </div>
            ))}
          </div>
        ) : requests && requests.length > 0 ? (
          <div className="space-y-3">
            {requests.map((req) => (
              <div
                key={req.id}
                className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">
                        {req.user_name}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          req.status === "pending"
                            ? "bg-amber-50 text-amber-700"
                            : req.status === "approved"
                              ? "bg-green-50 text-green-700"
                              : "bg-red-50 text-red-700"
                        }`}
                      >
                        {req.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 mt-0.5">
                      {req.user_email}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Requested{" "}
                      {new Date(req.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>

                  {req.status === "pending" && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => approve.mutate(req.id)}
                        disabled={approve.isPending}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                      >
                        {approve.isPending ? "..." : "Approve"}
                      </button>
                      <button
                        onClick={() => deny.mutate(req.id)}
                        disabled={deny.isPending}
                        className="px-4 py-2 bg-gray-100 text-gray-600 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
                      >
                        {deny.isPending ? "..." : "Deny"}
                      </button>
                    </div>
                  )}
                </div>

                {(approve.isError || deny.isError) && (
                  <p className="text-sm text-red-600 mt-2">
                    {approve.error?.message || deny.error?.message || "Action failed"}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-gray-400">
            <p className="text-sm">
              No {filter ? `${filter} ` : ""}requests found.
            </p>
          </div>
        )}
      </main>
    </>
  );
}
