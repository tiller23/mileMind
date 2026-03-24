"use client";

import { useState } from "react";
import { ApiError, strava } from "@/lib/api";
import { useStravaStatus, useStravaSync, useStravaDisconnect } from "@/lib/hooks";
import { formatDistance } from "@/lib/units";
import type { PreferredUnits } from "@/lib/types";

/** Strava brand orange per their brand guidelines. */
const STRAVA_ORANGE = "#FC4C02";

function StravaLogo({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg
      className={className}
      style={style}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" />
    </svg>
  );
}

interface StravaConnectProps {
  units?: PreferredUnits;
  onMileageSuggestion?: (km: number) => void;
}

export function StravaConnect({
  units = "metric",
  onMileageSuggestion,
}: StravaConnectProps) {
  const { data: status, isLoading } = useStravaStatus();
  const sync = useStravaSync();
  const disconnect = useStravaDisconnect();
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{
    imported: number;
    mileage: number | null;
  } | null>(null);

  async function handleConnect() {
    setConnectError(null);
    try {
      const data = await strava.connect();
      sessionStorage.setItem("strava_oauth_state", data.state);
      sessionStorage.setItem("strava_oauth_state_token", data.state_token);
      window.location.href = data.auth_url;
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        setConnectError("Strava integration is not configured yet.");
      } else {
        setConnectError("Failed to start Strava connection. Please try again.");
      }
    }
  }

  function handleSync() {
    setSyncResult(null);
    sync.mutate(undefined, {
      onSuccess: (data) => {
        setSyncResult({
          imported: data.imported_count,
          mileage: data.suggested_weekly_mileage_km,
        });
        if (data.suggested_weekly_mileage_km && onMileageSuggestion) {
          onMileageSuggestion(data.suggested_weekly_mileage_km);
        }
      },
    });
  }

  function handleDisconnect() {
    disconnect.mutate(undefined, {
      onSuccess: () => {
        setConfirmDisconnect(false);
        setSyncResult(null);
      },
    });
  }

  if (isLoading) return null;

  // Not connected
  if (!status?.connected) {
    return (
      <div className="border border-gray-200 rounded-xl p-5 bg-white">
        <div className="flex items-center gap-3 mb-3">
          <StravaLogo className="w-6 h-6" style={{ color: STRAVA_ORANGE }} />
          <h3 className="font-semibold text-gray-900">Connect Strava</h3>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Import your recent runs to auto-fill your weekly mileage and track
          plan vs. actual progress.
        </p>
        <button
          onClick={handleConnect}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white transition-colors shadow-sm"
          style={{ backgroundColor: STRAVA_ORANGE }}
        >
          <StravaLogo className="w-4 h-4" />
          Connect with Strava
        </button>
        {connectError && (
          <p className="text-sm text-red-600 mt-3">{connectError}</p>
        )}
        <p className="text-[10px] text-gray-400 mt-3">
          Powered by Strava. We only read your activities &mdash; we never post
          or modify anything on your Strava account.
        </p>
      </div>
    );
  }

  // Connected
  const lastSync = status.last_sync
    ? new Date(status.last_sync).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Never";

  return (
    <div className="border border-gray-200 rounded-xl p-5 bg-white">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <StravaLogo className="w-5 h-5" style={{ color: STRAVA_ORANGE }} />
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">
              Strava Connected
            </h3>
            <p className="text-xs text-gray-400">
              Last sync: {lastSync}
            </p>
          </div>
        </div>
        <span className="w-2 h-2 rounded-full bg-green-400" aria-label="Connected" role="status" />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={handleSync}
          disabled={sync.isPending}
          className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
        >
          {sync.isPending ? "Syncing..." : "Sync Now"}
        </button>
        {!confirmDisconnect ? (
          <button
            onClick={() => setConfirmDisconnect(true)}
            className="px-3 py-1.5 text-gray-400 hover:text-red-500 text-sm transition-colors"
          >
            Disconnect
          </button>
        ) : (
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleDisconnect}
              disabled={disconnect.isPending}
              className="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-sm font-medium hover:bg-red-100 disabled:opacity-50 transition-colors"
            >
              {disconnect.isPending ? "..." : "Confirm"}
            </button>
            <button
              onClick={() => setConfirmDisconnect(false)}
              className="px-3 py-1.5 text-gray-400 hover:text-gray-600 text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* Sync result feedback */}
      {syncResult && (
        <div className="mt-3 text-sm">
          {syncResult.imported > 0 ? (
            <p className="text-green-600">
              Imported {syncResult.imported} new{" "}
              {syncResult.imported === 1 ? "activity" : "activities"}.
            </p>
          ) : (
            <p className="text-gray-500">Already up to date.</p>
          )}
          {syncResult.mileage && (
            <p className="text-blue-600 mt-1">
              Based on your Strava data, your average weekly mileage is{" "}
              <strong>
                {units === "imperial"
                  ? `${(syncResult.mileage * 0.621371).toFixed(0)} mi`
                  : `${syncResult.mileage.toFixed(0)} km`}
              </strong>
              .
            </p>
          )}
        </div>
      )}

      <p className="text-[10px] text-gray-400 mt-3">
        Powered by Strava
      </p>
    </div>
  );
}
