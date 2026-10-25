"use client";

import type { PolicyConfig, Quote } from "@contracts/api";
import { useEffect, useRef, useState } from "react";
import { fmt, timeOf } from "@/lib/format";
import type { ChatMessage, QuoteStatus } from "@/lib/useDemo";

// ---------------------------------------------------------------- policy

export function PolicyCard({
  load,
  save,
}: {
  load: () => Promise<PolicyConfig>;
  save: (p: PolicyConfig) => Promise<PolicyConfig>;
}) {
  const [policy, setPolicy] = useState<PolicyConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    load().then(setPolicy).catch(() => {});
    // Load once; `load` is a fresh closure every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = (patch: Partial<PolicyConfig>) => {
    if (!policy) return;
    const next = { ...policy, ...patch };
    setPolicy(next);
    setSaving(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setPolicy(await save(next));
      } finally {
        setSaving(false);
      }
    }, 300);
  };

  return (
    <section className="rounded-2xl border border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Wallet policy</h2>
        <span className="text-xs text-ink-3">{saving ? "Saving…" : "Enforced by guardrail · not the AI"}</span>
      </div>
      {!policy ? (
        <div className="mt-4 h-28 animate-pulse rounded-xl bg-paper-2" />
      ) : (
        <div className="mt-4 space-y-5">
          <Slider
            label="Max daily budget"
            value={Number(policy.max_daily_budget)}
            min={20}
            max={300}
            step={5}
            onChange={(v) => update({ max_daily_budget: fmt(v) })}
          />
          <Slider
            label="Max per item"
            value={Number(policy.max_per_item)}
            min={5}
            max={150}
            step={5}
            onChange={(v) => update({ max_per_item: fmt(v) })}
          />
          <label className="flex cursor-pointer items-center justify-between">
            <span className="text-sm">
              Verified merchants only
              <span className="block text-xs text-ink-3">Requires an on-ledger Local_Merchant_KYC credential</span>
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={policy.require_verified_credential}
              onClick={() => update({ require_verified_credential: !policy.require_verified_credential })}
              className={`relative h-6 w-11 shrink-0 rounded-full transition ${policy.require_verified_credential ? "bg-matcha" : "bg-line"}`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${policy.require_verified_credential ? "left-[22px]" : "left-0.5"}`}
              />
            </button>
          </label>
        </div>
      )}
    </section>
  );
}

function Slider(props: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between text-sm">
        <span>{props.label}</span>
        <span className="tabular-nums font-semibold">{props.value} RLUSD</span>
      </div>
      <input
        type="range"
        className="mt-2 w-full"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
    </label>
  );
}

// ---------------------------------------------------------------- chat

const SUGGESTIONS = ["Plan a relaxed afternoon in Arashiyama under $100", "Any good souvenir shops nearby?"];

export function ChatPanel({ messages, busy, onSend }: { messages: ChatMessage[]; busy: boolean; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Scroll only the message box; scrollIntoView would also scroll the page column.
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  const send = (t: string) => {
    if (!t.trim() || busy) return;
    onSend(t.trim());
    setText("");
  };

  return (
    <section className="flex flex-col rounded-2xl border border-line bg-card">
      <div className="border-b border-line px-5 py-3">
        <h2 className="font-semibold">Trip planner</h2>
      </div>
      <div ref={box} className="max-h-72 min-h-40 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <p className="text-sm text-ink-3">Tell the agent where you&apos;re going, for how long, and your budget.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : ""}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed animate-slide-in ${
                m.role === "user"
                  ? "bg-ink text-paper"
                  : m.tone === "warning"
                    ? "border border-amber/40 bg-amber-soft"
                    : "bg-indigo-soft"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy && <div className="text-xs text-ink-3">Agent is working…</div>}
      </div>
      <div className="border-t border-line p-3">
        <div className="mb-2 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => send(s)}
              className="rounded-full border border-line px-3 py-1 text-xs text-ink-2 hover:border-ink-3 disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
          className="flex gap-2"
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Where to?"
            className="min-w-0 flex-1 rounded-xl border border-line bg-paper px-3 py-2 text-sm outline-none focus:border-ink-3"
          />
          <button disabled={busy || !text.trim()} className="rounded-xl bg-ink px-4 py-2 text-sm font-medium text-paper disabled:opacity-40">
            Send
          </button>
        </form>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- quotes

const STATUS_CHIP: Record<QuoteStatus, { label: string; cls: string } | null> = {
  quoted: null,
  booked: { label: "Booked · in escrow", cls: "bg-matcha text-white" },
  blocked: { label: "Blocked by guardrail", cls: "bg-torii text-white" },
  refunded: { label: "Refunded", cls: "bg-ink-3 text-white" },
};

export function QuoteList({
  quotes,
  status,
  confirmations,
  busy,
  onBook,
}: {
  quotes: Quote[];
  status: Record<string, QuoteStatus>;
  confirmations: Record<string, string>;
  busy: boolean;
  onBook: (ids: string[]) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const seen = useRef<Set<string>>(new Set());

  // Pre-select newly quoted items from verified merchants.
  useEffect(() => {
    const add = quotes.filter((q) => !seen.current.has(q.invoice_id));
    if (!add.length) return;
    add.forEach((q) => seen.current.add(q.invoice_id));
    setSelected((s) => new Set([...s, ...add.filter((q) => q.merchant_verified).map((q) => q.invoice_id)]));
  }, [quotes]);

  const bookable = quotes.filter((q) => selected.has(q.invoice_id) && status[q.invoice_id] === "quoted");
  const total = bookable.reduce((s, q) => s + Number(q.amount), 0);
  const viator = bookable.reduce((s, q) => s + Number(q.viator_price ?? q.amount), 0);

  return (
    <section className="rounded-2xl border border-line bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Itinerary</h2>
        <span className="text-xs text-ink-3">Signed 402 quotes · prices locked</span>
      </div>
      {quotes.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-3">
          Quotes from local merchants will appear here.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {quotes.map((q) => {
            const st = status[q.invoice_id] ?? "quoted";
            const chip = STATUS_CHIP[st];
            const savings = q.viator_price ? Math.round((1 - Number(q.amount) / Number(q.viator_price)) * 100) : null;
            return (
              <li
                key={q.invoice_id}
                className={`flex items-center gap-4 rounded-2xl border p-4 animate-slide-in ${
                  st === "blocked" ? "animate-shake border-torii/50 bg-torii-soft" : st === "refunded" ? "border-line opacity-60" : "border-line"
                }`}
              >
                <input
                  type="checkbox"
                  aria-label={`Select ${q.title}`}
                  disabled={st !== "quoted"}
                  checked={selected.has(q.invoice_id) && st === "quoted"}
                  onChange={(e) =>
                    setSelected((s) => {
                      const n = new Set(s);
                      e.target.checked ? n.add(q.invoice_id) : n.delete(q.invoice_id);
                      return n;
                    })
                  }
                  className="h-4 w-4 accent-ink"
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs text-ink-3">
                    {timeOf(q.slot_start)} · {q.merchant_name}
                  </div>
                  <div className={`font-medium ${st === "refunded" ? "line-through" : ""}`}>{q.title}</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {q.merchant_verified ? (
                      <span className="rounded-full bg-matcha-soft px-2 py-0.5 text-xs text-matcha">✓ Verified local</span>
                    ) : (
                      <span className="rounded-full bg-amber-soft px-2 py-0.5 text-xs text-amber">Unverified</span>
                    )}
                    {chip && <span className={`rounded-full px-2 py-0.5 text-xs ${chip.cls}`}>{chip.label}</span>}
                    {confirmations[q.invoice_id] && st === "booked" && (
                      <span className="rounded-full bg-paper-2 px-2 py-0.5 tabular-nums text-xs">#{confirmations[q.invoice_id]}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  {q.viator_price && <div className="text-xs text-ink-3 line-through">{fmt(q.viator_price)}</div>}
                  <div className="text-lg font-semibold">{fmt(q.amount)}</div>
                  {savings !== null && <div className="text-xs text-matcha">−{savings}%</div>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-4 flex items-center justify-between gap-4">
        <div className="text-sm">
          {bookable.length > 0 && (
            <>
              <span className="font-semibold">{fmt(total)} RLUSD</span>
              {viator > total && <span className="ml-2 text-matcha">saves {fmt(viator - total)} vs Viator</span>}
            </>
          )}
        </div>
        <button
          disabled={busy || bookable.length === 0}
          onClick={() => onBook(bookable.map((q) => q.invoice_id))}
          className="rounded-full bg-torii px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-torii/90 disabled:opacity-40"
        >
          Book itinerary{bookable.length > 0 ? ` (${bookable.length})` : ""}
        </button>
      </div>
    </section>
  );
}
