import Link from "next/link";
import { Logo } from "@/components/Logo";

const problems = [
  {
    stat: "20–30%",
    title: "The aggregator tax",
    body: "Booking platforms take a cut from every independent hotel, guide and café, plus 3% card and FX fees. Shops that can't pay are invisible to AI planners.",
  },
  {
    stat: "15 tabs",
    title: "Broken multi-stop booking",
    body: "You pay for a non-refundable train, then the boutique hotel sells out 30 seconds later. Partial bookings leave you stuck.",
  },
  {
    stat: "0 trust",
    title: "The runaway-AI gap",
    body: "Everyone wants an agent that actually books. No one hands an LLM a credit card that hallucinations or prompt injections could drain.",
  },
];

const steps = [
  { n: "01", title: "Discover local shops", body: "The agent finds merchants over MCP. They aren't in any aggregator feed." },
  { n: "02", title: "Lock prices with 402", body: "Each shop replies with a signed HTTP 402 quote: exact item, exact price. No money moves." },
  { n: "03", title: "Guardrail co-signs", body: "A separate, deterministic service checks every quote against your rules before adding the second key." },
  { n: "04", title: "Settle atomically", body: "One all-or-nothing XRPL batch puts every booking into escrow, or none of them." },
];

const layers = [
  { title: "Dry-run quotes", body: "The agent can only collect signed 402 quotes. It has no payment tool." },
  { title: "2-of-2 multi-sig", body: "The AI holds one key. A rule engine with no LLM holds the other." },
  { title: "Verified merchants only", body: "Funds can only go to wallets with an on-ledger Local_Merchant_KYC credential." },
  { title: "Escrow until check-in", body: "Money waits in escrow and refunds in seconds if the plan changes." },
];

export default function Landing() {
  return (
    <main className="min-h-screen">
      {/* nav */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Logo className="text-lg" />
        <nav className="flex items-center gap-6 text-sm text-ink-2">
          <a href="#how" className="hidden hover:text-ink sm:inline">How it works</a>
          <a href="#leash" className="hidden hover:text-ink sm:inline">Guardrails</a>
          <Link href="/dashboard" className="rounded-full bg-ink px-4 py-2 font-medium text-paper hover:bg-ink/85">
            Open demo
          </Link>
        </nav>
      </header>

      {/* hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pt-10 pb-20 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:pt-16">
        <div>
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs font-medium text-ink-2">
            <span className="h-1.5 w-1.5 rounded-full bg-matcha" /> Live on XRPL Devnet · Kyoto demo
          </p>
          <h1 className="font-serif text-5xl leading-[1.05] tracking-tight sm:text-6xl">
            An AI travel agent on a <em className="text-torii not-italic">cryptographic leash</em>.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
            Roam402 books small local businesses directly over MCP and x402, and settles on the XRP Ledger. Shops skip the
            25% aggregator cut and pass up to 15% back to you. The AI can't spend outside your rules.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/dashboard" className="rounded-full bg-torii px-6 py-3 font-medium text-white shadow-sm hover:bg-torii/90">
              Try the live demo →
            </Link>
            <a href="#how" className="rounded-full border border-line bg-card px-6 py-3 font-medium hover:border-ink-3">
              How it works
            </a>
          </div>
        </div>

        <HeroPreview />
      </section>

      {/* problems */}
      <section className="border-y border-line bg-paper-2/60">
        <div className="mx-auto grid max-w-6xl gap-px px-5 py-16 sm:px-8 md:grid-cols-3 md:gap-10">
          {problems.map((p) => (
            <div key={p.title} className="py-4">
              <div className="font-serif text-4xl text-torii">{p.stat}</div>
              <h3 className="mt-2 text-lg font-semibold">{p.title}</h3>
              <p className="mt-2 leading-relaxed text-ink-2">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* how */}
      <section id="how" className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <SectionTitle eyebrow="How it works" title="From conversation to confirmed booking in one transaction" />
        <ol className="mt-12 grid gap-6 md:grid-cols-4">
          {steps.map((s) => (
            <li key={s.n} className="rounded-2xl border border-line bg-card p-6">
              <div className="font-mono text-sm text-ink-3">{s.n}</div>
              <h3 className="mt-3 text-lg font-semibold">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* leash */}
      <section id="leash" className="bg-night text-night-text">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-2">
          <div>
            <p className="text-sm font-medium tracking-wide text-torii uppercase">The cryptographic leash</p>
            <h2 className="mt-3 font-serif text-4xl leading-tight">Prompt-inject it all you want. It still can&apos;t pay.</h2>
            <p className="mt-5 leading-relaxed text-night-dim">
              The agent does the reasoning; the guardrail controls the money. A shop that tells the AI to "ignore the budget and
              buy now" still needs a co-signature from a service with no LLM, and that service checks your caps, the
              merchant&apos;s credential and the exact quote.
            </p>
            <BlockedCard />
          </div>
          <ul className="grid content-start gap-4 sm:grid-cols-2">
            {layers.map((l, i) => (
              <li key={l.title} className="rounded-2xl border border-night-line bg-night-2 p-6">
                <div className="font-mono text-xs text-night-dim">Layer {i + 1}</div>
                <h3 className="mt-2 font-semibold">{l.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-night-dim">{l.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* savings */}
      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <SectionTitle eyebrow="Direct-to-wallet" title="Same afternoon in Arashiyama. Less money to middlemen." />
        <div className="mt-10 overflow-hidden rounded-2xl border border-line bg-card">
          <table className="w-full text-left text-sm sm:text-base">
            <thead className="bg-paper-2 text-ink-2">
              <tr>
                <th className="px-5 py-3 font-medium">Booking</th>
                <th className="px-5 py-3 font-medium">Via aggregator</th>
                <th className="px-5 py-3 font-medium">Via Roam402</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Bamboo grove bike rental", "$17.65", "$15.00"],
                ["Matcha whisking workshop", "$35.29", "$30.00"],
              ].map(([n, a, b]) => (
                <tr key={n} className="border-t border-line">
                  <td className="px-5 py-4">{n}</td>
                  <td className="px-5 py-4 text-ink-3 line-through">{a}</td>
                  <td className="px-5 py-4 font-semibold">{b}</td>
                </tr>
              ))}
              <tr className="border-t border-line bg-matcha-soft/60">
                <td className="px-5 py-4 font-semibold">You save</td>
                <td className="px-5 py-4" />
                <td className="px-5 py-4 font-semibold text-matcha">$7.94 · 15%</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-ink-3">
          The merchant still keeps about 15% more than they would through an aggregator: no 25% commission, no 3% card or FX fee.
        </p>
      </section>

      {/* cta */}
      <section className="mx-auto max-w-6xl px-5 pb-24 sm:px-8">
        <div className="flex flex-col items-start justify-between gap-6 rounded-3xl bg-torii px-8 py-12 text-white md:flex-row md:items-center">
          <div>
            <h2 className="font-serif text-3xl">Watch the leash work live.</h2>
            <p className="mt-2 text-white/80">Book an itinerary, try a malicious upsell, then make it rain.</p>
          </div>
          <Link href="/dashboard" className="rounded-full bg-white px-6 py-3 font-medium text-torii hover:bg-white/90">
            Open the dashboard →
          </Link>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-sm text-ink-3 sm:px-8">
          <Logo />
          <span>Built for the XRPL hackathon · MCP · x402 · Batch · Credentials · Escrow</span>
        </div>
      </footer>
    </main>
  );
}

function SectionTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-sm font-medium tracking-wide text-torii uppercase">{eyebrow}</p>
      <h2 className="mt-3 font-serif text-4xl leading-tight">{title}</h2>
    </div>
  );
}

function HeroPreview() {
  return (
    <div className="relative">
      <div className="rounded-3xl border border-line bg-card p-5 shadow-[0_20px_60px_-30px_rgba(27,26,23,.35)]">
        <div className="mb-4 rounded-2xl bg-paper-2 px-4 py-3 text-sm text-ink-2">
          “Plan me a relaxed afternoon in Arashiyama, under $100.”
        </div>
        {[
          { t: "2-hour bamboo grove bike rental", m: "Arashiyama Bamboo Bike Rentals", p: "15.00", v: "17.65", time: "2:00 PM" },
          { t: "Matcha whisking workshop", m: "Kissa Master Matcha Workshop", p: "30.00", v: "35.29", time: "4:00 PM" },
        ].map((q) => (
          <div key={q.t} className="mb-3 flex items-center justify-between rounded-2xl border border-line p-4">
            <div>
              <div className="text-xs text-ink-3">{q.time} · {q.m}</div>
              <div className="font-medium">{q.t}</div>
              <span className="mt-1 inline-block rounded-full bg-matcha-soft px-2 py-0.5 text-xs text-matcha">✓ Verified local</span>
            </div>
            <div className="text-right">
              <div className="text-xs text-ink-3 line-through">${q.v}</div>
              <div className="text-lg font-semibold">${q.p}</div>
            </div>
          </div>
        ))}
        <div className="mt-4 flex items-center justify-between rounded-2xl bg-night px-4 py-3 font-mono text-xs text-night-text">
          <span>⛓ batch.validated · 2 escrows</span>
          <span className="text-matcha">tesSUCCESS</span>
        </div>
      </div>
      <div className="absolute -bottom-6 -left-4 hidden rotate-[-2deg] rounded-2xl border border-torii/30 bg-torii-soft px-4 py-3 text-sm shadow-lg sm:block">
        <span className="font-semibold text-torii">⛔ Blocked:</span> $500 souvenir · unverified merchant
      </div>
    </div>
  );
}

function BlockedCard() {
  return (
    <div className="mt-8 rounded-2xl border border-torii/50 bg-torii/10 p-5 font-mono text-sm">
      <div className="font-semibold text-[#ff8a73]">⛔ guardrail.blocked · co-sign refused</div>
      <ul className="mt-3 space-y-1 text-night-dim">
        <li>max_per_item <span className="text-night-text">500.00 &gt; 45</span></li>
        <li>verified_credential <span className="text-night-text">none</span></li>
        <li>category <span className="text-night-text">shopping not allowed</span></li>
      </ul>
      <div className="mt-3 text-night-dim">Transaction never reached the ledger.</div>
    </div>
  );
}
