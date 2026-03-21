import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="max-w-2xl text-center space-y-8">
        <h1 className="text-5xl font-bold tracking-tight">
          Mile<span className="text-blue-600">Mind</span>
        </h1>
        <p className="text-xl text-gray-600 leading-relaxed">
          AI-powered training plans built by agents, grounded in exercise
          science. Two AI agents collaborate — a planner creates your plan, a
          reviewer scores it for safety — so every workout is backed by real
          physiology.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/login"
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Get Started
          </Link>
          <Link
            href="/login"
            className="px-6 py-3 border border-gray-300 rounded-lg font-medium hover:bg-gray-100 transition-colors"
          >
            Sign In
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 pt-8 text-left">
          <div className="space-y-2">
            <div className="text-2xl font-bold text-blue-600">2 Agents</div>
            <p className="text-sm text-gray-500">
              Planner + Reviewer negotiate until your plan scores 70+ across
              safety, progression, specificity, and feasibility.
            </p>
          </div>
          <div className="space-y-2">
            <div className="text-2xl font-bold text-blue-600">100% Math</div>
            <p className="text-sm text-gray-500">
              TSS, CTL, ATL, ACWR, VO2max — all computed by deterministic
              Python models. The AI never guesses a number.
            </p>
          </div>
          <div className="space-y-2">
            <div className="text-2xl font-bold text-blue-600">Your Goals</div>
            <p className="text-sm text-gray-500">
              From couch-to-5K to sub-3 marathon. Plans adapt to your fitness
              level, injury history, and risk tolerance.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
