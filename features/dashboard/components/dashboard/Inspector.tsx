"use client";

import type { InspectorEvent, PolicyDecision } from "@contracts/api";
import { clock, short } from "@/lib/format";
import type { SignerState } from "@/lib/useDemo";

const LEVEL: Record<string, { dot: string; text: string }> = {
  info: { dot: "bg-night-dim", text: "text-night-text" },
  success: { dot: "bg-[#6fcf6a]", text: "text-night-text" },
  warning: { dot: "bg-[#f0b44c]", text: "text-[#f6d394]" },
  blocked: { dot: "bg-torii", text: "text-[#ff8a73]" },
  error: { dot: "bg-torii", text: "text-[#ff8a73]" },
};

const SOURCE_ICON: Record<string, string> = { agent: "🤖", merchant: "🏮", guardrail: "🛡", ledger: "⛓", system: "☁" };

export function Inspector({
  events,
  signers,
}: {
  events: InspectorEvent[];
  signers: { agent: SignerState; guardrail: SignerState; ledger: SignerState };
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-2xl bg-night text-night-text">
      <div className="flex items-center justify-between border-b border-night-line px-5 py-3">
        <h2 className="font-semibold">XRPL &amp; Guardrail Inspector</h2>
        <span className="font-mono text-xs text-night-dim">{events.length} events</span>
      </div>
      <SignerStatus signers={signers} />
      <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {events.length === 0 && (
          <li className="px-1 py-10 text-center text-sm text-night-dim">
            Waiting for activity. Ask the agent for a plan or run a demo scenario.
          </li>
        )}
        {events.map((e) =>
          e.level === "blocked" ? <BlockedEvent key={e.id} event={e} /> : <EventRow key={e.id} event={e} />,
        )}
      </ol>
    </section>
  );
}

function SignerStatus({ signers }: { signers: { agent: SignerState; guardrail: SignerState; ledger: SignerState } }) {
  const items: { label: string; state: SignerState }[] = [
    { label: "Agent key", state: signers.agent },
    { label: "Guardrail key", state: signers.guardrail },
    { label: "On ledger", state: signers.ledger },
  ];
  const glyph: Record<SignerState, { g: string; cls: string }> = {
    idle: { g: "○", cls: "text-night-dim border-night-line" },
    pending: { g: "…", cls: "text-[#f6d394] border-[#f0b44c]/40" },
    signed: { g: "✓", cls: "text-[#9be696] border-[#6fcf6a]/40 bg-[#6fcf6a]/10" },
    refused: { g: "✕", cls: "text-[#ff8a73] border-torii/60 bg-torii/15" },
  };
  return (
    <div className="grid grid-cols-3 gap-2 border-b border-night-line px-4 py-3">
      {items.map((it) => (
        <div key={it.label} className={`rounded-xl border px-3 py-2 transition ${glyph[it.state].cls}`}>
          <div className="text-[11px] tracking-wide text-night-dim uppercase">{it.label}</div>
          <div className="font-mono text-lg leading-tight">{glyph[it.state].g}</div>
        </div>
      ))}
      <div className="col-span-3 font-mono text-[11px] text-night-dim">2-of-2 multi-sig · master key disabled</div>
    </div>
  );
}

function EventRow({ event: e }: { event: InspectorEvent }) {
  const lv = LEVEL[e.level] ?? LEVEL.info;
  return (
    <li className="flex gap-3 rounded-xl bg-night-2 px-3 py-2.5 animate-slide-in">
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${lv.dot}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2 font-mono text-[11px] text-night-dim">
          <span>
            {SOURCE_ICON[e.source]} {e.type}
          </span>
          <span>{clock(e.ts)}</span>
        </div>
        <div className={`mt-0.5 text-sm ${lv.text}`}>{e.message}</div>
        {e.tx_hash && (
          <a
            href={e.explorer_url ?? "#"}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block font-mono text-xs text-[#8fb0ff] hover:underline"
          >
            tx {short(e.tx_hash)} ↗
          </a>
        )}
      </div>
    </li>
  );
}

function BlockedEvent({ event: e }: { event: InspectorEvent }) {
  const decision = (e.data as { decision?: PolicyDecision }).decision;
  return (
    <li className="animate-slide-in rounded-xl border-2 border-torii bg-torii/15 p-4">
      <div className="flex items-baseline justify-between font-mono text-[11px] text-[#ff8a73]">
        <span>🛡 {e.type}</span>
        <span>{clock(e.ts)}</span>
      </div>
      <div className="mt-1 text-lg font-semibold text-white">⛔ {e.message}</div>
      {decision && (
        <ul className="mt-3 space-y-1.5">
          {decision.violations.map((v, i) => (
            <li key={i} className="rounded-lg bg-night/60 px-3 py-2 text-sm">
              <span className="font-mono text-xs text-[#ff8a73]">{v.rule}</span>
              <div className="text-night-text">{v.detail}</div>
              {(v.expected || v.actual) && (
                <div className="font-mono text-xs text-night-dim">
                  expected {v.expected} · got <span className="text-white">{v.actual}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 text-xs text-night-dim">No co-signature → the transaction never reached the ledger.</div>
    </li>
  );
}
