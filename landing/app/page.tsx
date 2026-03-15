"use client";

import { useState } from "react";

function WaitlistForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [project, setProject] = useState("");
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, project }),
      });
      if (!res.ok) throw new Error("Failed to submit");
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="text-center py-12 animate-fade-in">
        <div className="text-accent text-lg font-medium mb-2">
          You&apos;re on the list.
        </div>
        <p className="text-muted text-sm">
          We&apos;ll be in touch when it&apos;s your turn. In the meantime, keep
          building.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 max-w-md mx-auto">
      <input
        type="text"
        placeholder="Your name"
        required
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-foreground placeholder:text-muted focus:outline-none focus:border-accent transition-colors"
      />
      <input
        type="email"
        placeholder="Email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-foreground placeholder:text-muted focus:outline-none focus:border-accent transition-colors"
      />
      <textarea
        placeholder="What are you working on? (optional)"
        value={project}
        onChange={(e) => setProject(e.target.value)}
        rows={3}
        className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-foreground placeholder:text-muted focus:outline-none focus:border-accent transition-colors resize-none"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="w-full py-3 bg-accent text-background font-medium rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 cursor-pointer"
      >
        {status === "loading" ? "Joining..." : "Request Early Access"}
      </button>
      {status === "error" && (
        <p className="text-red-400 text-sm text-center">
          Something went wrong. Please try again.
        </p>
      )}
    </form>
  );
}

export default function Home() {
  return (
    <main className="min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 bg-background/80 backdrop-blur-md border-b border-border">
        <div className="max-w-5xl mx-auto px-6 py-4 flex justify-between items-center">
          <span className="text-lg font-semibold tracking-wider">GEM</span>
          <a
            href="#waitlist"
            className="text-sm text-accent hover:text-accent-hover transition-colors"
          >
            Join Waitlist
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6 md:pt-44 md:pb-32">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.1] animate-fade-in">
            Know exactly who
            <br />
            <span className="text-accent">to talk to next.</span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-muted max-w-2xl mx-auto leading-relaxed animate-fade-in-delay-1">
            The entertainment industry runs on relationships most creators
            can&apos;t see. GEM maps the smartest path to representation,
            buyers, producers, and capital for your specific project.
          </p>
          <div className="mt-10 animate-fade-in-delay-2">
            <a
              href="#waitlist"
              className="inline-block px-8 py-3.5 bg-accent text-background font-medium rounded-lg hover:bg-accent-hover transition-colors"
            >
              Request Early Access
            </a>
          </div>
        </div>
      </section>

      {/* Problem */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-sm uppercase tracking-widest text-accent mb-8">
            The Problem
          </h2>
          <div className="space-y-6 text-lg leading-relaxed text-muted">
            <p>
              Hollywood is opaque by design. The people who could change your
              career are behind walls you don&apos;t even know exist. Most
              creators spend years sending material to the wrong people, in the
              wrong order, with no strategy.
            </p>
            <p>
              The information about who&apos;s actually buying, who&apos;s
              looking for what, and which path makes sense for{" "}
              <em>your</em> specific project — that information exists.
              It&apos;s just locked inside the heads of a small number of
              insiders.
            </p>
            <p className="text-foreground font-medium">GEM unlocks it.</p>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 px-6 border-t border-border bg-surface">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-sm uppercase tracking-widest text-accent mb-12">
            How It Works
          </h2>
          <div className="grid gap-10 md:grid-cols-3">
            {[
              {
                step: "01",
                title: "Submit your project",
                desc: "Share your script, concept, or IP. Tell us what you're looking for — representation, production, distribution, financing, or all of it.",
              },
              {
                step: "02",
                title: "Get your map",
                desc: "GEM analyzes your material against the current landscape and returns the most relevant people and companies to approach — prioritized and strategic.",
              },
              {
                step: "03",
                title: "Move with clarity",
                desc: "Stop guessing. Know which reps are actively looking for your genre. Which producers have deals at the right studios. Which buyers are actually in-market.",
              },
            ].map((item) => (
              <div key={item.step}>
                <div className="text-accent font-mono text-sm mb-3">
                  {item.step}
                </div>
                <h3 className="text-lg font-medium mb-2">{item.title}</h3>
                <p className="text-muted text-sm leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What You Get */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-sm uppercase tracking-widest text-accent mb-12">
            What You Get
          </h2>
          <div className="grid gap-6 md:grid-cols-2">
            {[
              {
                title: "Targeted allies",
                desc: "The specific reps, producers, executives, and companies most likely to respond to your material.",
              },
              {
                title: "Prioritized outreach",
                desc: "Not just who — but in what order, and why. A sequenced strategy, not a spray-and-pray list.",
              },
              {
                title: "Market intelligence",
                desc: "Who's buying in your space right now. What's selling. Where the real opportunities are.",
              },
              {
                title: "A smarter path forward",
                desc: "Whether you need a manager first or should go direct to producers. Whether your project is a feature, series, or something else entirely.",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="p-6 border border-border rounded-lg hover:border-accent/30 transition-colors"
              >
                <h3 className="font-medium mb-2">{item.title}</h3>
                <p className="text-muted text-sm leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Who It's For */}
      <section className="py-20 px-6 border-t border-border bg-surface">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-sm uppercase tracking-widest text-accent mb-8">
            Who It&apos;s For
          </h2>
          <div className="space-y-4 text-muted">
            {[
              "Screenwriters with material ready to go out",
              "Creators developing original IP across film, TV, and audio",
              "Authors, journalists, and IP holders exploring adaptation",
              "Independent producers looking for the right partners",
              "Anyone tired of guessing how the industry actually works",
            ].map((item) => (
              <div key={item} className="flex items-start gap-3">
                <span className="text-accent mt-1.5 text-xs">&#9670;</span>
                <span className="text-sm leading-relaxed">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Waitlist */}
      <section id="waitlist" className="py-24 px-6 border-t border-border">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
            Stop guessing. Start moving.
          </h2>
          <p className="text-muted mb-10 max-w-lg mx-auto">
            GEM is in early development. Request access and be among the first
            to use it when we launch.
          </p>
          <WaitlistForm />
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-border">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted">
          <span className="tracking-wider font-medium text-foreground">
            GEM
          </span>
          <span>
            &copy; {new Date().getFullYear()} GEM Studio. All rights reserved.
          </span>
        </div>
      </footer>
    </main>
  );
}
