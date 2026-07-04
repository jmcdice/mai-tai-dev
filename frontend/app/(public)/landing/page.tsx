"use client";

import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen bg-background">
      {/* Background gradient blobs - fixed position so they show through all sections */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -top-1/2 -right-1/4 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-primary/30 to-accent2/30 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-accent2/20 to-primary/20 blur-3xl" />
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 z-50 w-full border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Mai-Tai"
              className="h-10 w-10 rounded-full"
            />
            <span className="text-xl font-bold text-foreground">Mai-Tai</span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
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
            <h1 className="text-4xl font-bold leading-tight text-foreground sm:text-5xl lg:text-6xl">
              Your AI coding agent,{" "}
              <span className="bg-gradient-to-r from-primary to-accent2 bg-clip-text text-transparent">
                in your pocket.
              </span>
            </h1>
            <p className="mt-6 text-lg text-muted-foreground sm:text-xl">
              Talk to your agent from anywhere — your phone, your laptop, or the
              beach.
            </p>
            <div className="mt-8">
              <Link
                href="/register"
                className="inline-block rounded-lg bg-primary px-8 py-3 text-center text-lg font-medium text-primary-foreground transition hover:bg-primary/90"
              >
                Get Started
              </Link>
            </div>
          </div>

          {/* Right: Phone Mockup */}
          <div className="flex justify-center">
            <div className="relative">
              {/* Phone Frame */}
              <div className="relative mx-auto w-[280px] rounded-[2rem] border-[4px] border-border bg-card shadow-2xl">
                {/* Notch */}
                <div className="absolute left-1/2 top-0 z-10 h-4 w-16 -translate-x-1/2 rounded-b-lg bg-surface2" />
                {/* Screen */}
                <div className="relative aspect-[9/19.5] overflow-hidden rounded-[1.75rem] bg-background">
                  <img
                    src="/mobile.png"
                    alt="Mai-Tai on mobile"
                    className="h-full w-full object-cover object-top"
                  />
                </div>
              </div>
              {/* Glow effect */}
              <div className="absolute -inset-4 -z-10 rounded-[2.5rem] bg-gradient-to-r from-primary/20 to-accent2/20 blur-2xl" />
            </div>
          </div>
        </div>
      </section>

      {/* Origin Story - Short */}
      <section className="relative z-10 border-t border-border py-16">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <p className="text-lg text-muted-foreground leading-relaxed">
            Sometimes you gotta step away, man. Go surf, grab a coffee, live
            your life. Mai-tai keeps you connected to your agent so you can
            check in, answer questions, and ship features — from wherever,
            whenever.
          </p>
        </div>
      </section>

      {/* How It Works */}
      <section className="relative z-10 border-t border-border py-24">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold text-foreground sm:text-4xl">
            How It Works
          </h2>
          <div className="mt-16 grid gap-8 sm:grid-cols-3">
            {/* Step 1 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/20 text-3xl">
                🐳
              </div>
              <h3 className="mt-6 text-xl font-semibold text-foreground">Spin Up an Agent</h3>
              <p className="mt-2 text-muted-foreground">
                Create a workspace, pick a template — research, coding, assistant — and mai-tai
                launches a Docker container running Claude Code, connected to your workspace.
              </p>
            </div>
            {/* Step 2 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/20 text-3xl">
                🏄
              </div>
              <h3 className="mt-6 text-xl font-semibold text-foreground">
                Step Away
              </h3>
              <p className="mt-2 text-muted-foreground">
                Your agent works autonomously. It sends you updates, asks questions,
                and remembers what it learns — even across restarts.
              </p>
            </div>
            {/* Step 3 */}
            <div className="text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/20 text-3xl">
                📱
              </div>
              <h3 className="mt-6 text-xl font-semibold text-foreground">
                Check In
              </h3>
              <p className="mt-2 text-muted-foreground">
                Pull up mai-tai on your phone. Answer questions, unblock your agent,
                and ship — from wherever you are.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative z-10 border-t border-border py-24">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold text-foreground sm:text-4xl">
            Everything You Need
          </h2>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { icon: "🐳", title: "Docker-per-agent", desc: "Each workspace gets its own isolated container. Start, stop, and restart agents from the UI." },
              { icon: "🧠", title: "Persistent Memory", desc: "Agents write lessons to a mounted volume. They get smarter over time and remember across restarts." },
              { icon: "💻", title: "Coding Agent", desc: "Clones your GitHub repo, writes code, opens PRs — just give it a repo URL and a PAT." },
              { icon: "🔄", title: "Real-time", desc: "WebSocket-powered messaging. Updates arrive instantly on any device." },
              { icon: "📱", title: "Mobile-first", desc: "Designed for checking in from your phone. Compact, fast, thumb-friendly." },
              { icon: "🏠", title: "Self-hosted", desc: "Runs entirely on your machine. No data leaves your network." },
            ].map((f) => (
              <div key={f.title} className="rounded-xl border border-border/50 bg-card/30 p-6">
                <div className="text-2xl">{f.icon}</div>
                <h3 className="mt-3 font-semibold text-foreground">{f.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Works With */}
      <section className="relative z-10 border-t border-border py-24">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-3xl font-bold text-foreground sm:text-4xl">
            Works With Your Agent
          </h2>
          <p className="mt-4 text-center text-muted-foreground">
            Any MCP-compatible AI coding agent
          </p>
          <div className="mt-12 flex flex-wrap items-center justify-center gap-6">
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">🤖</span>
              <span className="font-medium text-foreground">Claude Desktop</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">💻</span>
              <span className="font-medium text-foreground">Claude Code</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">✨</span>
              <span className="font-medium text-foreground">Gemini</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">⚡</span>
              <span className="font-medium text-foreground">Cursor</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">🚀</span>
              <span className="font-medium text-foreground">Augment</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-3">
              <span className="text-xl">🔧</span>
              <span className="font-medium text-foreground">Any MCP Agent</span>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative z-10 border-t border-border py-24">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <h2 className="text-3xl font-bold text-foreground sm:text-4xl">
            Ready to try it?
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            100% local. Runs entirely on your machine. No data leaves your
            network.
          </p>
          <div className="mt-8">
            <Link
              href="/register"
              className="inline-block rounded-lg bg-primary px-8 py-3 text-lg font-medium text-primary-foreground transition hover:bg-primary/90"
            >
              Get Started
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border py-8">
        <div className="mx-auto max-w-6xl px-4 text-center text-sm text-faint">
          © {new Date().getFullYear()} Mai-Tai
        </div>
      </footer>
    </div>
  );
}
