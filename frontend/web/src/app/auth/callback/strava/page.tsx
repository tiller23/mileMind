"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { strava } from "@/lib/api";

function StravaCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const returnedState = searchParams.get("state");
    if (!code) {
      setError("No authorization code received from Strava.");
      return;
    }

    const savedState = sessionStorage.getItem("strava_oauth_state");
    const savedStateToken = sessionStorage.getItem("strava_oauth_state_token");
    sessionStorage.removeItem("strava_oauth_state");
    sessionStorage.removeItem("strava_oauth_state_token");

    if (!savedState || savedState !== returnedState) {
      setError("Invalid OAuth state. Please try connecting again.");
      return;
    }

    if (!savedStateToken) {
      setError("Missing OAuth state token. Please try connecting again.");
      return;
    }

    async function exchangeCode(authCode: string) {
      try {
        await strava.callback({
          code: authCode,
          state: savedStateToken!,
        });
        // Redirect back to onboarding/settings where they initiated connect
        router.push("/onboarding");
      } catch {
        setError("Failed to connect Strava. Please try again.");
      }
    }

    exchangeCode(code);
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4">
        <p className="text-red-600 mb-4">{error}</p>
        <Link href="/onboarding" className="text-blue-600 underline">
          Back to settings
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <div
        className="animate-spin w-8 h-8 border-4 border-gray-200 rounded-full"
        style={{ borderTopColor: "#FC4C02" }}
        role="status"
        aria-label="Connecting Strava"
      />
      <p className="mt-4 text-gray-500">Connecting Strava...</p>
    </div>
  );
}

export default function StravaCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen">
          <p className="text-gray-500">Loading...</p>
        </div>
      }
    >
      <StravaCallbackInner />
    </Suspense>
  );
}
