"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

function GoogleCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code) {
      setError("No authorization code received from Google.");
      return;
    }

    async function exchangeCode(code: string, state: string | null) {
      try {
        const res = await fetch(`${API_BASE}/auth/google/callback`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, state }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => null);
          setError(body?.detail ?? "Authentication failed");
          return;
        }

        router.push("/dashboard");
      } catch {
        setError("Network error during authentication");
      }
    }

    exchangeCode(code, state);
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <p className="text-red-600 mb-4">{error}</p>
        <a href="/login" className="text-blue-600 underline">
          Try again
        </a>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <div className="animate-spin w-8 h-8 border-4 border-gray-200 border-t-blue-600 rounded-full" />
      <p className="mt-4 text-gray-500">Signing in...</p>
    </div>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen">
          <p className="text-gray-500">Loading...</p>
        </div>
      }
    >
      <GoogleCallbackInner />
    </Suspense>
  );
}
