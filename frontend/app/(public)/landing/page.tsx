"use client";

import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen bg-gray-900">
      {/* Background gradient blobs - fixed position so they show through all sections */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -top-1/2 -right-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-indigo-500/30 to-purple-600/30 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-purple-500/20 to-indigo-600/20 blur-3xl" />
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 z-50 w-full border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Mai-Tai"
              className="h-10 w-10 rounded-full"
            />
            <span className="text-xl font-bold text-white">Mai-Tai</span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm font-medium text-gray-300 transition hover:text-white"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 flex min-h-screen items-center pt-20">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 md:grid-cols-2 md:items-center">
          {/* Left: Copy */}
          <div className="text-center md:text-left">
            <h1 className="text-4xl font-bold leading-tight text-white sm:text-5xl lg:text-6xl">
              Your AI coding agent,{" "}
              <span className="bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
                in your pocket.
              </span>
            </h1>
            <p className="mt-6 text-lg text-gray-400 sm:text-xl">
              Talk to your agent from anywhere — your phone, your laptop, or the
              beach.
            </p>
            <div className="mt-8">
              <Link
                href="/register"
                className="inline-block rounded-lg bg-indigo-600 px-8 py-3 text-center text-lg font-medium text-white transition hover:bg-indigo-500"
              >
                Get Started
              </Link>
            </div>
          </div>

          {/* Right: Phone Mockup */}
          <div className="flex justify-center">
            <div className="relative">
              {/* Phone Frame */}
              <div className="relative mx-auto w-[280px] rounded-[2rem] border-[4px] border-gray-700 bg-gray-800 shadow-2xl">
                {/* Notch */}
                <div className="absolute left-1/2 top-0 z-10 h-4 w-16 -translate-x-1/2 rounded-b-lg bg-gray-700" />
                {/* Screen */}
                <div className="relative aspect-[9/19.5] overflow-hidden rounded-[1.75rem] bg-gray-900">
                  <img
                    src="/mobile.png"
                    alt="Mai-Tai on mobile"
                    className="h-full w-full object-cover object-top"
                  />
                </div>
              </div>
              {/* Glow effect */}
              <div className="absolute -inset-4 -z-10 rounded-[2.5rem] bg-gradient-to-r from-indigo-500/20 to-purple-500/20 blur-2xl" />
            </div>
          </div>
        </div>
      </section>

      {/* Origin Story - Short */}
      <section className="relative z-10 border-t border-gray-800 py-16">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <p className="text-lg text-gray-300 leading-relaxed">
            Sometimes you gotta step away, man. Go surf, grab a coffee, live
            your life. Mai-tai keeps you connected to your agent so you can
            check in, answer questions, and ship features — from wherever,
            whenever.
          </p>
        </div>
      </section>

      {/* How It Works */}
      <section className="relative z-10 border-t border-gray-800 py-24">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold text-white sm:text-4xl">
            How It Works
          </h2>
          <div className="mt-16 grid gap-8 sm:grid-cols-3">
            {/* Step 1 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600/20 text-3xl">
                🔌
              </div>
              <h3 className="mt-6 text-xl font-semibold text-white">Connect</h3>
              <p className="mt-2 text-gray-400">
                Add mai-tai to your AI agent via MCP. Works with Claude Desktop,
                Augment, and more.
              </p>
            </div>
            {/* Step 2 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600/20 text-3xl">
                🏄
              </div>
              <h3 className="mt-6 text-xl font-semibold text-white">
                Step Away
              </h3>
              <p className="mt-2 text-gray-400">
                Your agent keeps working while you live your life. Go surf,
                shop, or grab coffee.
              </p>
            </div>
            {/* Step 3 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-600/20 text-3xl">
                📱
              </div>
              <h3 className="mt-6 text-xl font-semibold text-white">
                Check In
              </h3>
              <p className="mt-2 text-gray-400">
                Pull up mai-tai on your phone. Answer questions, review
                progress, ship features.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Works With */}
      <section className="relative z-10 border-t border-gray-800 py-24">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold text-white sm:text-4xl">
            Works With Your Agent
          </h2>
          <p className="mt-4 text-center text-gray-400">
            Any MCP-compatible AI coding agent
          </p>
          <div className="mt-12 flex flex-wrap items-center justify-center gap-6">
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">🤖</span>
              <span className="font-medium text-white">Claude Desktop</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">💻</span>
              <span className="font-medium text-white">Claude Code</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">✨</span>
              <span className="font-medium text-white">Gemini</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">⚡</span>
              <span className="font-medium text-white">Cursor</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">🚀</span>
              <span className="font-medium text-white">Augment</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-gray-700 bg-gray-800/50 px-5 py-3">
              <span className="text-xl">🔧</span>
              <span className="font-medium text-white">Any MCP Agent</span>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative z-10 border-t border-gray-800 py-24">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <h2 className="text-3xl font-bold text-white sm:text-4xl">
            Ready to try it?
          </h2>
          <p className="mt-4 text-lg text-gray-400">
            100% local. Runs entirely on your machine. No data leaves your
            network.
          </p>
          <div className="mt-8">
            <Link
              href="/register"
              className="inline-block rounded-lg bg-indigo-600 px-8 py-3 text-lg font-medium text-white transition hover:bg-indigo-500"
            >
              Get Started
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-gray-800 py-8">
        <div className="mx-auto max-w-6xl px-4 text-center text-sm text-gray-500">
          © {new Date().getFullYear()} Mai-Tai
        </div>
      </footer>
    </div>
  );
}
