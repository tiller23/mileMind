import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-400/20 via-transparent to-transparent" />
        <nav className="relative max-w-6xl mx-auto px-4 py-6 flex items-center justify-between">
          <span className="text-2xl font-bold text-white tracking-tight">
            Mile<span className="text-blue-200">Mind</span>
          </span>
          <Link
            href="/login"
            className="text-sm font-medium text-blue-100 hover:text-white transition-colors"
          >
            Sign In
          </Link>
        </nav>

        <div className="relative max-w-4xl mx-auto px-4 pt-16 pb-24 text-center">
          <h1 className="text-5xl sm:text-6xl font-bold text-white tracking-tight leading-tight">
            Train smarter with
            <br />
            AI-powered plans
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-blue-100 max-w-2xl mx-auto leading-relaxed">
            Two AI agents collaborate to build your personalized running plan.
            Every workout is grounded in exercise science — not guesswork.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/login"
              className="px-8 py-3.5 bg-white text-blue-700 rounded-lg font-semibold hover:bg-blue-50 transition-colors shadow-lg shadow-blue-900/20"
            >
              Get Started Free
            </Link>
            <a
              href="#how-it-works"
              className="px-8 py-3.5 border border-blue-300/40 text-white rounded-lg font-medium hover:bg-white/10 transition-colors"
            >
              See How It Works
            </a>
          </div>
        </div>
      </header>

      {/* How it works */}
      <section id="how-it-works" className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">
            How MileMind works
          </h2>
          <p className="text-center text-gray-500 mb-16 max-w-xl mx-auto">
            A unique multi-agent approach ensures your plan is both creative and safe.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="relative p-6 rounded-xl bg-gray-50 border border-gray-100">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-lg mb-4">
                1
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Tell us about you
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                Your weekly mileage, goal race, experience level, and injury
                history. Takes about 2 minutes.
              </p>
            </div>

            <div className="relative p-6 rounded-xl bg-gray-50 border border-gray-100">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-lg mb-4">
                2
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                AI designs your plan
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                A Planner agent builds your training block. A Reviewer agent
                scores it on safety, progression, and specificity. They
                iterate until it passes.
              </p>
            </div>

            <div className="relative p-6 rounded-xl bg-gray-50 border border-gray-100">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-lg mb-4">
                3
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Start training
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                Get a week-by-week plan with every workout prescribed —
                distance, pace zone, and purpose. Backed by real physiology.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="text-3xl mb-3">🤖</div>
              <div className="font-semibold text-gray-900 mb-1">2 AI Agents</div>
              <p className="text-sm text-gray-500">
                Planner + Reviewer negotiate until your plan scores 70+ across
                all safety dimensions.
              </p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="text-3xl mb-3">📐</div>
              <div className="font-semibold text-gray-900 mb-1">Real Math</div>
              <p className="text-sm text-gray-500">
                TSS, VO2max, ACWR — computed by deterministic models. The AI
                never fabricates a number.
              </p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="text-3xl mb-3">🏃</div>
              <div className="font-semibold text-gray-900 mb-1">Any Level</div>
              <p className="text-sm text-gray-500">
                From first-time runners to experienced marathoners. Plans adapt
                to your fitness and goals.
              </p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">
              <div className="text-3xl mb-3">🔬</div>
              <div className="font-semibold text-gray-900 mb-1">Transparent</div>
              <p className="text-sm text-gray-500">
                See exactly how your plan was built. Full agent reasoning and
                scores visible in the debug view.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-white">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Ready to train smarter?
          </h2>
          <p className="text-gray-500 mb-8">
            Create your free account and generate your first AI-powered
            training plan in minutes.
          </p>
          <Link
            href="/login"
            className="inline-block px-8 py-3.5 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/20"
          >
            Get Started Free
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-gray-50 py-8">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between text-sm text-gray-400">
          <span>Mile<span className="text-blue-500">Mind</span></span>
          <span>&copy; {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
