import Link from "next/link";
import { Logo } from "@/components/Logo";

const steps = [
  { n: "1", title: "Say where and when", body: "Pick a destination and dates. Swanavi already knows your home airports, your pace and what you like." },
  { n: "2", title: "Swanavi plans the whole trip", body: "Flights in your time window, a hotel near the places you'll visit, and a day-by-day route with travel times." },
  { n: "3", title: "You review and book", body: "Local shops and small stays are paid from your wallet. Airlines and hotel chains open their own sites." },
];

const layers = [
  { title: "Quotes first, money later", body: "The agent can only collect signed price quotes. It has no payment tool." },
  { title: "Two keys, one with no AI", body: "The AI holds one key. A rule engine with no language model holds the other." },
  { title: "Verified merchants only", body: "Funds can only go to wallets with an on-ledger merchant credential." },
  { title: "Escrow until check-in", body: "Money waits in escrow and refunds in seconds if the plan changes." },
];

export default function Landing() {
  return (
    <main className="swan-app min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Logo className="text-lg" />
        <nav className="flex items-center gap-5 text-sm">
          <a href="#how" className="swan-muted hidden hover:text-black sm:inline">How it works</a>
          <a href="#trust" className="swan-muted hidden hover:text-black sm:inline">Why trust it</a>
          <Link href="/plan/new" className="swan-btn inline-flex items-center min-h-11!">Plan a trip</Link>
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pt-10 pb-20 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:pt-16">
        <div>
          <p className="swan-eyebrow">Your AI travel agent</p>
          <h1 className="mt-4 text-5xl leading-[1.02] sm:text-6xl">Tell Swanavi where. It plans and books the whole trip.</h1>
          <p className="swan-muted mt-6 max-w-xl text-lg leading-relaxed">
            Flights, a hotel near the places you want to see, and a day-by-day plan with the travel times filled in. One
            screen to review. One checklist to book.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/plan/new" className="swan-btn inline-flex items-center">Plan a trip</Link>
            <a href="#how" className="swan-btn-ghost inline-flex items-center">How it works</a>
          </div>
          <p className="swan-muted mt-6 text-sm">Demo data for Kyoto. Local payments settle on the XRP Ledger devnet.</p>
        </div>
        <HeroPreview />
      </section>

      <section id="how" className="border-y swan-line">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
          <SectionTitle eyebrow="How it works" title="Three steps. Swanavi does the middle one." />
          <ol className="mt-12 grid gap-6 md:grid-cols-3">
            {steps.map((step) => (
              <li key={step.n} className="swan-card p-6">
                <div className="swan-marker-badge" aria-hidden="true">{step.n}</div>
                <h3 className="mt-4 text-lg">{step.title}</h3>
                <p className="swan-muted mt-2 text-sm leading-relaxed">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <SectionTitle eyebrow="Local shops, paid directly" title="Same afternoon in Arashiyama. Less money to middlemen." />
        <div className="swan-card mt-10 overflow-hidden">
          <table className="w-full text-left text-sm sm:text-base">
            <thead className="swan-surface swan-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Booking</th>
                <th className="px-5 py-3 font-medium">Via aggregator</th>
                <th className="px-5 py-3 font-medium">Via Swanavi</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Bamboo grove bike rental", "$17.65", "$15.00"],
                ["Matcha whisking workshop", "$35.29", "$30.00"],
              ].map(([name, before, after]) => (
                <tr key={name} className="border-t swan-line">
                  <td className="px-5 py-4">{name}</td>
                  <td className="swan-muted px-5 py-4 line-through">{before}</td>
                  <td className="px-5 py-4 font-semibold">{after}</td>
                </tr>
              ))}
              <tr className="swan-surface border-t swan-line">
                <td className="px-5 py-4 font-semibold">You save</td>
                <td className="px-5 py-4" />
                <td className="px-5 py-4 font-semibold">$7.94 · 15%</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="swan-muted mt-4 text-sm">
          The shop keeps about 15% more than through an aggregator: no 25% commission, no 3% card or FX fee.
        </p>
      </section>

      <section id="trust" className="bg-night text-night-text">
        <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-2">
          <div>
            <p className="swan-eyebrow text-night-dim!">Why you can trust it with money</p>
            <h2 className="mt-3 text-4xl leading-tight">Prompt-inject it all you want. It still can&apos;t pay.</h2>
            <p className="mt-5 leading-relaxed text-night-dim">
              The agent does the reasoning; a guardrail controls the money. A shop that tells the AI to &ldquo;ignore the budget
              and buy now&rdquo; still needs a co-signature from a service with no language model, and that service checks
              your caps, the merchant&apos;s credential and the exact quote.
            </p>
            <BlockedCard />
            <Link href="/dashboard" className="mt-6 inline-flex items-center rounded-full border border-night-line px-5 py-3 text-sm font-semibold hover:bg-night-2">
              Open the ledger inspector
            </Link>
          </div>
          <ul className="grid content-start gap-4 sm:grid-cols-2">
            {layers.map((layer, index) => (
              <li key={layer.title} className="rounded-2xl border border-night-line bg-night-2 p-6">
                <div className="text-xs font-semibold tracking-wide text-night-dim uppercase">Layer {index + 1}</div>
                <h3 className="mt-2 text-base">{layer.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-night-dim">{layer.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
        <div className="swan-invert flex flex-col items-start justify-between gap-6 rounded-3xl px-8 py-12 md:flex-row md:items-center">
          <div>
            <h2 className="text-3xl">Ready when you are.</h2>
            <p className="mt-2 opacity-80">Two minutes of setup, then every trip starts with one sentence.</p>
          </div>
          <Link href="/plan/new" className="inline-flex items-center rounded-full bg-white px-6 py-3 font-semibold text-black">
            Plan a trip
          </Link>
        </div>
      </section>

      <footer className="border-t swan-line">
        <div className="swan-muted mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-sm sm:px-8">
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
      <p className="swan-eyebrow">{eyebrow}</p>
      <h2 className="mt-3 text-4xl leading-tight">{title}</h2>
    </div>
  );
}

function HeroPreview() {
  const stops = [
    ["1:10 PM", "Land at Kansai", "Train or bus · 1h 15m"],
    ["3:00 PM", "Check in at Hyatt Place Arashiyama", "Train or bus · 31 min"],
    ["4:06 PM", "Kinkaku-ji", ""],
  ];
  return (
    <div className="swan-card p-5 shadow-[0_24px_60px_-30px_rgba(0,0,0,.35)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="swan-eyebrow">Kyoto, Japan</p>
          <p className="mt-1 text-2xl font-bold tracking-tight">Sat 14 – Mon 16 Nov</p>
        </div>
        <p className="text-2xl font-bold tracking-tight">$1,730</p>
      </div>
      <div className="mt-4 grid gap-2 text-sm">
        <div className="swan-surface flex items-center justify-between rounded-xl px-3 py-2">
          <span>Japan Airlines · SFO → KIX</span>
          <span className="swan-muted">9:05 AM → 1:10 PM <span className="swan-badge ml-1">+1 day</span></span>
        </div>
        <div className="swan-surface flex items-center justify-between rounded-xl px-3 py-2">
          <span>Hyatt Place Arashiyama</span>
          <span className="swan-muted">$180 / night</span>
        </div>
      </div>
      <p className="swan-eyebrow mt-5">Sat 14</p>
      <ol className="mt-2">
        {stops.map(([time, title, leg]) => (
          <li key={title} className="text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium">{title}</span>
              <span className="swan-muted">{time}</span>
            </div>
            {leg ? <p className="swan-muted my-1.5 border-l-2 border-current pl-3 text-xs">{leg}</p> : null}
          </li>
        ))}
      </ol>
      <div className="mt-4 flex items-center justify-between rounded-xl bg-night px-4 py-3 text-xs text-night-text">
        <span>Activities paid from wallet · 2 escrows</span>
        <span className="font-semibold">Validated</span>
      </div>
    </div>
  );
}

function BlockedCard() {
  return (
    <div className="mt-8 rounded-2xl border border-night-line bg-night-2 p-5 font-mono text-sm">
      <div className="font-semibold text-night-text">Blocked · co-sign refused</div>
      <ul className="mt-3 space-y-1 text-night-dim">
        <li>max_per_item <span className="text-night-text">500.00 &gt; 45</span></li>
        <li>verified_credential <span className="text-night-text">none</span></li>
        <li>category <span className="text-night-text">shopping not allowed</span></li>
      </ul>
      <div className="mt-3 text-night-dim">Transaction never reached the ledger.</div>
    </div>
  );
}
