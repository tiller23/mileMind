import Link from "next/link";
import { Logo } from "@/components/Logo";
import { ShieldCheckIcon, BeakerIcon, TargetIcon, EyeIcon } from "@/components/Icons";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/15 via-transparent to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-indigo-500/10 via-transparent to-transparent" />

        <nav className="relative max-w-6xl mx-auto px-4 py-6 flex items-center justify-between">
          <Logo size="md" variant="light" />
          <Link
            href="/login"
            className="text-sm font-medium text-slate-300 hover:text-white transition-colors"
          >
            Sign In
          </Link>
        </nav>

        <div className="relative max-w-4xl mx-auto px-4 pt-20 pb-28 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/10 border border-blue-400/20 text-sm text-blue-300 mb-6">
            <span>Personalized running plans</span>
            <span className="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-400/30 text-amber-300 text-xs font-medium">
              Invite Only
            </span>
          </div>
          <h1 className="text-5xl sm:text-6xl font-bold text-white tracking-tight leading-tight">
            Train smarter.
            <br />
            <span className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
              Run stronger.
            </span>
          </h1>
          <p className="mt-6 text-lg text-slate-400 max-w-2xl mx-auto leading-relaxed">
            AI designs your plan. A second AI reviews it for safety.
            Every decision transparent, every workout backed by science.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/login"
              className="px-8 py-3.5 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-500 transition-all shadow-lg shadow-blue-600/25 hover:shadow-blue-500/30"
            >
              Get Started
            </Link>
            <Link
              href="/demo"
              className="px-8 py-3.5 border border-slate-600 text-slate-300 rounded-xl font-medium hover:bg-white/5 transition-colors"
            >
              View Demo Plans
            </Link>
          </div>
        </div>

        {/* Gradient fade to white */}
        <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-[#f8fafc] to-transparent" />
      </header>

      {/* How it works */}
      <section id="how-it-works" className="py-20">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">
            Three steps to your plan
          </h2>
          <p className="text-center text-gray-500 mb-16 max-w-xl mx-auto">
            From profile to plan in minutes. No spreadsheets, no guesswork.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[
              {
                step: "1",
                title: "Share your background",
                desc: "Quick questions about your running — weekly mileage, goals, injury history, and how hard you want to push.",
              },
              {
                step: "2",
                title: "AI builds your plan",
                desc: "One AI designs your training block, another independently reviews it for safety and balance. You can see exactly how every decision was made.",
              },
              {
                step: "3",
                title: "Start training",
                desc: "A clear week-by-week calendar with every run laid out — distance, effort, and why it matters.",
              },
            ].map((item) => (
              <div key={item.step} className="relative">
                <div className="flex items-start gap-4 p-6 rounded-2xl bg-white border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white flex items-center justify-center font-bold text-lg shrink-0 shadow-sm">
                    {item.step}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-1.5">
                      {item.title}
                    </h3>
                    <p className="text-sm text-gray-500 leading-relaxed">
                      {item.desc}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 bg-gradient-to-b from-transparent via-slate-50 to-transparent">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">
            Why runners trust MileMind
          </h2>
          <p className="text-center text-gray-500 mb-16 max-w-xl mx-auto">
            Not another cookie-cutter plan.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              {
                icon: <ShieldCheckIcon className="w-6 h-6" />,
                title: "Reviewed for safety",
                desc: "Every plan is independently checked for safe progression and injury risk before you see it.",
                accent: "from-emerald-500 to-emerald-600",
                iconBg: "bg-emerald-50 text-emerald-600",
              },
              {
                icon: <BeakerIcon className="w-6 h-6" />,
                title: "Science-backed",
                desc: "Your training load, recovery, and pacing are calculated by proven models — never guesswork.",
                accent: "from-blue-500 to-blue-600",
                iconBg: "bg-blue-50 text-blue-600",
              },
              {
                icon: <TargetIcon className="w-6 h-6" />,
                title: "Built for you",
                desc: "From first-time runners to experienced marathoners. Your plan adapts to your fitness, schedule, and goals.",
                accent: "from-amber-500 to-amber-600",
                iconBg: "bg-amber-50 text-amber-600",
              },
              {
                icon: <EyeIcon className="w-6 h-6" />,
                title: "See the reasoning",
                desc: "Curious why a workout is there? You can see the full decision-making process.",
                accent: "from-violet-500 to-violet-600",
                iconBg: "bg-violet-50 text-violet-600",
              },
            ].map((f) => (
              <div
                key={f.title}
                className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm hover:shadow-md transition-all group"
              >
                <div className={`w-11 h-11 rounded-xl ${f.iconBg} flex items-center justify-center mb-4`}>
                  {f.icon}
                </div>
                <div className="font-semibold text-gray-900 mb-1.5">{f.title}</div>
                <p className="text-sm text-gray-500 leading-relaxed">
                  {f.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Ready to train smarter?
          </h2>
          <p className="text-gray-500 mb-8">
            Sign up and get your first personalized plan in minutes.
          </p>
          <Link
            href="/login"
            className="inline-block px-8 py-3.5 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-600/20"
          >
            Get Started
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 py-8">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between text-sm text-gray-400">
          <Logo size="sm" />
          <span>&copy; {new Date().getFullYear()} MileMind</span>
        </div>
      </footer>
    </div>
  );
}
