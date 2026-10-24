"use client";

import Link from "next/link";
import { Logo } from "@/components/Logo";
import { Inspector } from "@/components/dashboard/Inspector";
import { ChatPanel, PolicyCard, QuoteList } from "@/components/dashboard/TravellerPanel";
import { fmt } from "@/lib/format";
import { useDemo } from "@/lib/useDemo";

export default function Dashboard() {
  const { client, state, sendChat, checkout, scenario, getPolicy, putPolicy } = useDemo();
  const w = state.wallet;

  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-card px-4 py-3 sm:px-6">
        <Link href="/">
          <Logo />
        </Link>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Stat label="Wallet" value={w ? `${fmt(w.balance)} RLUSD` : "—"} />
          <Stat label="In escrow" value={w ? fmt(w.locked_in_escrow) : "—"} />
          <Stat label="Saved vs Viator" value={fmt(state.saved)} accent />
          <span className="rounded-full border border-line px-2.5 py-1 font-mono text-xs text-ink-2">
            {client.mode === "mock" ? "mock data" : "XRPL Devnet"}
          </span>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-4 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto lg:pr-1 [&>*]:shrink-0">
          <PolicyCard load={getPolicy} save={putPolicy} />
          <ChatPanel messages={state.chat} busy={state.busy} onSend={sendChat} />
          <QuoteList
            quotes={state.quotes}
            status={state.status}
            confirmations={state.confirmations}
            busy={state.busy}
            onBook={checkout}
          />
        </div>
        <div className="flex min-h-[28rem] flex-col">
          <Inspector events={state.events} signers={state.signers} />
        </div>
      </main>

      <footer className="flex flex-wrap items-center gap-3 border-t border-line bg-card px-4 py-3 sm:px-6">
        <span className="mr-auto text-xs font-medium tracking-wide text-ink-3 uppercase">Demo</span>
        <DemoButton onClick={() => scenario("malicious-upsell")} disabled={state.busy} tone="torii">
          Simulate malicious upsell
        </DemoButton>
        <DemoButton onClick={() => scenario("rainstorm")} disabled={state.busy} tone="indigo">
          Simulate rainstorm at 2 PM
        </DemoButton>
        <DemoButton onClick={() => scenario("reset")} disabled={state.busy} tone="plain">
          Reset
        </DemoButton>
      </footer>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span className={`rounded-full px-3 py-1 ${accent ? "bg-matcha-soft text-matcha" : "bg-paper-2"}`}>
      <span className="text-ink-3">{label}</span> <span className="font-mono font-semibold">{value}</span>
    </span>
  );
}

function DemoButton({
  children,
  onClick,
  disabled,
  tone,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled: boolean;
  tone: "torii" | "indigo" | "plain";
}) {
  const cls = {
    torii: "bg-torii text-white hover:bg-torii/90",
    indigo: "bg-indigo text-white hover:bg-indigo/90",
    plain: "border border-line bg-card hover:border-ink-3",
  }[tone];
  return (
    <button onClick={onClick} disabled={disabled} className={`rounded-full px-4 py-2 text-sm font-medium disabled:opacity-40 ${cls}`}>
      {children}
    </button>
  );
}
