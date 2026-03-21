"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";
import { useUser } from "@/lib/hooks";

export function Navbar() {
  const { data: user } = useUser();
  const router = useRouter();

  async function handleLogout() {
    try {
      await auth.logout();
    } catch {
      // Cookies may already be cleared server-side; navigate anyway
    }
    router.push("/");
  }

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/dashboard" className="text-xl font-bold tracking-tight">
          Mile<span className="text-blue-600">Mind</span>
        </Link>

        <div className="flex items-center gap-4">
          {user && (
            <>
              <Link
                href="/dashboard"
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                Dashboard
              </Link>
              <Link
                href="/onboarding"
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                Settings
              </Link>
              <span className="text-sm text-gray-500">{user.name}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-500 hover:text-gray-900"
              >
                Logout
              </button>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
