"use client";

import type { BookingChannel, BookingLine, Suggestion, TripView, UserProfile, Violation } from "@contracts/api";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LockIcon } from "@/components/trip/LockIcon";
import { hostOf } from "@/lib/booking";
import { getClient } from "@/lib/client";
import { formatDay, formatMoney, hotelPrice, suggestionTitle, summarizeFlight } from "@/lib/format";
import { groupForBooking, linkOf, mergeLines, quoteOf, withBookings } from "@/lib/tripBooking";

type Step = "waiting" | "done" | "refused" | "failed";
type Steps = { agent: Step; guardrail: Step; ledger: Step };
type RowStatus = BookingLine["status"] | "booking" | "waiting";

const IDLE: Steps = { agent: "waiting", guardrail: "waiting", ledger: "waiting" };
const STEP_EVENTS: Record<string, Partial<Steps>> = {
  "tx.signed.agent": { agent: "done" },
  "guardrail.approved": { guardrail: "done" },
  "guardrail.blocked": { guardrail: "refused" },
  "batch.validated": { ledger: "done" },
  "batch.failed": { ledger: "failed" },
};
const STEP_MARK: Record<Step, string> = { waiting: "○", done: "✓", refused: "✕", failed: "✕" };
const STATUS_TEXT: Record<Exclude<RowStatus, "booked">, string> = {
  blocked: "✕ Blocked by your guardrail",
  failed: "✕ Failed",
  needs_user: "! Needs your input",
  booking: "Booking…",
  waiting: "Not booked yet",
};

export function ReviewBook({ tripId, onBack }: { tripId: string; onBack: () => void }) {
  const [view, setView] = useState<TripView | null>(null);
  const [profile, setProfile] = useState<UserProfile | null | undefined>(undefined);
  const [running, setRunning] = useState<BookingChannel | null>(null);
  const [steps, setSteps] = useState<Steps | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [announcement, setAnnouncement] = useState("");

  async function refresh(): Promise<TripView> {
    const next = await getClient().getTrip(tripId);
    setView(next);
    return next;
  }

  useEffect(() => {
    getClient().getTrip(tripId).then(setView);
    getClient().getProfile().then(setProfile).catch(() => setProfile(null));
  }, [tripId]);

  useEffect(() => {
    const stop = getClient().subscribe((event) => {
      const step = STEP_EVENTS[event.type];
      if (step) setSteps((current) => ({ ...(current ?? IDLE), ...step }));
      const line = event.data?.line as BookingLine | undefined;
      if (!line) return;
      setView((current) => current && { ...current, bookings: mergeLines(current.bookings, [line]) });
      setFresh((current) => new Set(current).add(line.suggestion_id));
      setAnnouncement(event.message);
    });
    return () => {
      stop();
    };
  }, []);

  async function book(channel: BookingChannel, travellers?: string[]) {
    if (running) return;
    setRunning(channel);
    setFresh(new Set());
    if (channel === "wallet") setSteps(IDLE);
    setAnnouncement(channel === "wallet" ? "Paying from your wallet…" : "Booking with providers…");
    try {
      await getClient().bookTrip(tripId, { channel, travellers });
      setAnnouncement(outcome(await refresh(), channel));
    } catch {
      setAnnouncement("Swan could not reach the booking service. Nothing changed. Try again.");
    } finally {
      setRunning(null);
    }
  }

  async function raiseLimits(rows: Suggestion[]) {
    const client = getClient();
    const [policy, wallet] = await Promise.all([client.getPolicy(), client.getWallet()]);
    const amounts = rows.map((row) => Number(quoteOf(row)?.amount ?? 0));
    const total = amounts.reduce((sum, amount) => sum + amount, 0);
    await client.putPolicy({
      ...policy,
      max_per_item: Math.max(Number(policy.max_per_item), ...amounts).toFixed(2),
      max_daily_budget: Math.max(Number(policy.max_daily_budget), Number(wallet.spent_today) + total).toFixed(2),
    });
    await book("wallet");
  }

  async function signInDemo() {
    await getClient().demoSignIn();
    setProfile(await getClient().getProfile());
    setAnnouncement("Signed in with the demo profile.");
  }

  if (!view?.proposal) return <p className="convo-status" role="status">Loading your trip…</p>;

  const proposal = withBookings(view.proposal, view.bookings);
  const groups = groupForBooking(proposal);
  const lines = new Map(view.bookings.map((line) => [line.suggestion_id, line]));
  const payable = [...groups.wallet, ...groups.external];
  const booked = payable.filter((row) => row.status === "booked").length;
  const signedOut = profile === null;
  const party = view.conversation.brief.travellers ?? 1;
  const walletOpen = groups.wallet.filter((row) => row.status !== "booked");
  const externalOpen = groups.external.filter((row) => row.status !== "booked");
  const walletTotal = walletOpen.reduce((sum, row) => sum + Number(quoteOf(row)?.amount ?? 0), 0);
  const currency = (groups.wallet[0] && quoteOf(groups.wallet[0])?.currency) || "RLUSD";
  const blocked = walletOpen.flatMap((row) => {
    const line = lines.get(row.id);
    return line?.channel === "wallet" && line.status === "blocked" ? [{ row, line }] : [];
  });
  const violations = dedupe(blocked.flatMap(({ line }) => (line.channel === "wallet" ? line.violations : [])));
  const firstNeedsInput = externalOpen.find((row) => lines.get(row.id)?.status === "needs_user")?.id;
  const statusOf = (row: Suggestion, channel: BookingChannel): RowStatus => {
    if (row.status === "booked") return "booked";
    if (running === channel && !fresh.has(row.id)) return "booking";
    return lines.get(row.id)?.status ?? "waiting";
  };
  const retrying = externalOpen.some((row) => lines.has(row.id));

  return (
    <div className="review">
      <header className="home-bar">
        <Link href="/" className="home-brand">Swanavi</Link>
        <button type="button" className="swan-btn-ghost" onClick={onBack}>Back to proposal</button>
      </header>
      <main className="review-body">
        <h1>Review and book</h1>
        <section className="review-progress" aria-labelledby="progress-heading">
          <h2 id="progress-heading" className="sr-only">Progress</h2>
          <p className="proposal-total"><strong>{booked} of {payable.length}</strong> booked</p>
          <progress max={payable.length || 1} value={booked} aria-label={`${booked} of ${payable.length} booked`} />
          <p className="proposal-note" role="status" aria-live="polite">{announcement}</p>
          {payable.length > 0 && booked === payable.length ? (
            <p className="review-done">Everything is booked. Your confirmation codes are below and on the trip.</p>
          ) : null}
        </section>

        {signedOut ? (
          <section className="review-gate" aria-labelledby="gate-heading">
            <h2 id="gate-heading">Sign in to book</h2>
            <p>Swan books in your name and pays from your wallet. Your trip stays in this browser.</p>
            <div className="proposal-actions">
              <button type="button" className="swan-btn" onClick={signInDemo}>Use demo profile</button>
              <Link className="swan-btn-ghost" href="/signin">Sign in with email</Link>
            </div>
          </section>
        ) : null}

        {groups.wallet.length ? (
          <section className="review-group" aria-labelledby="wallet-heading">
            <h2 id="wallet-heading">Pay from your Swan wallet</h2>
            <p className="swan-muted">Swan&apos;s agent signs first. Your guardrail co-signs only if the payment fits your limits.</p>
            <ul className="review-list">
              {groups.wallet.map((row) => (
                <BookingRow key={row.id} row={row} line={lines.get(row.id)} status={statusOf(row, "wallet")} />
              ))}
            </ul>
            <ol className="review-steps" aria-label="Payment steps">
              {(["agent", "guardrail", "ledger"] as const).map((key) => {
                const state = (steps ?? stepsFrom(groups.wallet, lines))[key];
                return (
                  <li key={key} data-state={state}>
                    <span aria-hidden="true">{STEP_MARK[state]}</span> {STEP_LABEL[key][state]}
                  </li>
                );
              })}
            </ol>
            {violations.length ? (
              <div className="review-alert">
                <p><strong>Your guardrail blocked this payment. Nothing was paid.</strong></p>
                <ul>
                  {violations.map((item) => <li key={`${item.rule}-${item.invoice_id}`}>{explain(item, currency)}</li>)}
                </ul>
                <div className="proposal-actions">
                  <button type="button" className="swan-btn" onClick={() => raiseLimits(blocked.map(({ row }) => row))}>
                    Raise my limits to cover {formatMoney(walletTotal, currency)}, then pay
                  </button>
                  {blocked.map(({ row }) => {
                    const link = linkOf(row);
                    return link ? (
                      <a key={row.id} className="swan-btn-ghost" href={link} target="_blank" rel="noreferrer">
                        Book {suggestionTitle(row)} on {hostOf(link)} instead
                      </a>
                    ) : null;
                  })}
                </div>
              </div>
            ) : null}
            {walletOpen.length && !violations.length ? (
              <button
                type="button"
                className="swan-btn"
                disabled={signedOut}
                aria-disabled={running !== null || undefined}
                onClick={() => book("wallet")}
              >
                Pay {formatMoney(walletTotal, currency)} from wallet
              </button>
            ) : null}
          </section>
        ) : null}

        {groups.external.length ? (
          <section className="review-group" aria-labelledby="external-heading">
            <h2 id="external-heading">Book with providers</h2>
            <p className="swan-muted">Swan&apos;s booking agent books these with the airline, hotel, or venue.</p>
            <ul className="review-list">
              {groups.external.map((row) => {
                const status = statusOf(row, "external");
                const link = linkOf(row);
                return (
                  <BookingRow key={row.id} row={row} line={lines.get(row.id)} status={status}>
                    {status === "failed" ? (
                      <div className="proposal-actions">
                        <button type="button" className="swan-btn-ghost" aria-disabled={running !== null || undefined} onClick={() => book("external")}>
                          Retry {suggestionTitle(row)}
                        </button>
                        {link ? <a className="swan-btn-ghost" href={link} target="_blank" rel="noreferrer">Book on {hostOf(link)}</a> : null}
                      </div>
                    ) : null}
                    {row.id === firstNeedsInput && status === "needs_user" ? (
                      <TravellerForm party={party} known={profile?.name ?? ""} busy={running !== null} onSubmit={(names) => book("external", names)} />
                    ) : null}
                  </BookingRow>
                );
              })}
            </ul>
            {externalOpen.length ? (
              <button
                type="button"
                className="swan-btn"
                disabled={signedOut}
                aria-disabled={running !== null || undefined}
                onClick={() => book("external")}
              >
                {retrying ? `Try the ${externalOpen.length} left again` : `Book ${externalOpen.length} with providers`}
              </button>
            ) : null}
          </section>
        ) : null}

        {groups.free.length ? (
          <section className="review-group" aria-labelledby="free-heading">
            <h2 id="free-heading">Nothing to book</h2>
            <ul className="review-list">
              {groups.free.map((row) => (
                <li key={row.id} className="review-row">
                  <p className="trip-card-title">{suggestionTitle(row)}</p>
                  <p className="swan-muted">Free entry. Just show up.</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {groups.waiting.length ? (
          <section className="review-group" aria-labelledby="waiting-heading">
            <h2 id="waiting-heading">Not accepted yet</h2>
            <p>
              {groups.waiting.length} suggestion{groups.waiting.length === 1 ? " is" : "s are"} still waiting for your review and will not be booked:{" "}
              {groups.waiting.map(suggestionTitle).join(", ")}.
            </p>
            <button type="button" className="swan-btn-ghost" onClick={onBack}>Back to proposal</button>
          </section>
        ) : null}
      </main>
    </div>
  );
}

const STEP_LABEL: Record<keyof Steps, Record<Step, string>> = {
  agent: { waiting: "Swan's agent signs", done: "Swan's agent signed (1 of 2)", refused: "Swan's agent did not sign", failed: "Swan's agent did not sign" },
  guardrail: { waiting: "Your guardrail co-signs", done: "Your guardrail co-signed (2 of 2)", refused: "Your guardrail refused to co-sign", failed: "Your guardrail did not answer" },
  ledger: { waiting: "The ledger settles the payment", done: "Paid and held in escrow", refused: "Nothing was submitted", failed: "The ledger did not settle the payment" },
};

function stepsFrom(rows: Suggestion[], lines: Map<string, BookingLine>): Steps {
  const states = rows.map((row) => (row.status === "booked" ? "booked" : lines.get(row.id)?.status));
  if (states.length && states.every((state) => state === "booked")) return { agent: "done", guardrail: "done", ledger: "done" };
  if (states.includes("blocked")) return { agent: "done", guardrail: "refused", ledger: "refused" };
  if (states.includes("failed")) return { agent: "done", guardrail: "done", ledger: "failed" };
  return IDLE;
}

function BookingRow({ row, line, status, children }: { row: Suggestion; line: BookingLine | undefined; status: RowStatus; children?: React.ReactNode }) {
  const code = line?.confirmation_code;
  return (
    <li className="review-row" data-status={status} id={`book-${row.id}`}>
      <div className="review-row-head">
        <p className="trip-card-title">{suggestionTitle(row)}</p>
        <p className="review-status">
          {status === "booked" ? <><LockIcon /> Booked{code ? ` · ${code}` : ""}</> : STATUS_TEXT[status]}
        </p>
      </div>
      <p className="swan-muted">{detail(row)}</p>
      {line?.error && status !== "booked" && status !== "booking" ? (
        <p className={status === "needs_user" ? undefined : "review-error"}>{line.error}</p>
      ) : null}
      {children}
    </li>
  );
}

function TravellerForm({ party, known, busy, onSubmit }: { party: number; known: string; busy: boolean; onSubmit: (names: string[]) => void }) {
  const [names, setNames] = useState<string[]>(() => Array.from({ length: party }, (_, index) => (index === 0 ? known : "")));
  const ready = names.every((name) => name.trim().length > 1);
  return (
    <form
      className="review-form"
      aria-label="Traveller names"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready && !busy) onSubmit(names.map((name) => name.trim()));
      }}
    >
      <p>Use full names as they appear on each passport.</p>
      {names.map((name, index) => (
        <label key={index} className="sheet-field">
          Traveller {index + 1}
          <input
            value={name}
            autoComplete={index === 0 ? "name" : "off"}
            onChange={(event) => setNames((current) => current.map((item, at) => (at === index ? event.target.value : item)))}
          />
        </label>
      ))}
      <button type="submit" className="swan-btn" disabled={!ready}>Save names and book</button>
    </form>
  );
}

function detail(row: Suggestion): string {
  if (row.kind === "flight") {
    const flight = summarizeFlight(row.item);
    return `${flight.route} · ${flight.departDay} ${flight.depart} · ${formatMoney(row.item.price, row.item.currency)}`;
  }
  if (row.kind === "hotel") {
    const quote = row.item.offer.quote;
    return quote ? `${quote.title} · ${formatMoney(quote.amount, quote.currency)}` : hotelPrice(row.item.offer);
  }
  const quote = row.item.quote;
  return quote ? `${formatDay(row.item.start.slice(0, 10))} · ${formatMoney(quote.amount, quote.currency)}` : `${formatDay(row.item.start.slice(0, 10))} · tickets from the venue`;
}

function explain(item: Violation, currency: string): string {
  const limit = item.expected?.replace(/^<=\s*/, "");
  const limitText = limit && !Number.isNaN(Number(limit)) ? formatMoney(limit, currency) : item.expected;
  const actual = item.actual && !Number.isNaN(Number(item.actual)) ? formatMoney(item.actual, currency) : item.actual;
  return limitText && actual ? `${item.detail}. Limit ${limitText}, this is ${actual}.` : `${item.detail}.`;
}

function dedupe(items: Violation[]): Violation[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.rule}-${item.invoice_id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function outcome(view: TripView, channel: BookingChannel): string {
  const lines = view.bookings.filter((line) => line.channel === channel);
  if (channel === "wallet") {
    if (lines.some((line) => line.status === "blocked")) return "Your guardrail blocked the wallet payment. Nothing was paid.";
    if (lines.some((line) => line.status === "failed")) return "The wallet payment did not settle. Nothing was charged.";
    return "Paid from your wallet.";
  }
  const failed = lines.filter((line) => line.status === "failed").length;
  const needs = lines.filter((line) => line.status === "needs_user").length;
  const parts = [`${lines.filter((line) => line.status === "booked").length} booked with providers.`];
  if (needs) parts.push(`${needs} need${needs === 1 ? "s" : ""} your input.`);
  if (failed) parts.push(`${failed} failed. Retry or book with the provider.`);
  return parts.join(" ");
}
