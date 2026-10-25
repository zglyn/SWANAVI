"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SwanMark } from "@/components/brand/SwanMark";
import { getClient } from "@/lib/client";
import { TRIP_MESSAGE_KEY } from "@/lib/tripDraft";

const CHIPS = [
  "Kyoto in November, 4 days",
  "A warm beach week under $2k",
  "Tokyo food trip with a friend",
  "Surprise me",
];

const PLACEHOLDERS = ["Where do you want to go?", ...CHIPS];

export default function HomePage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [placeholder, setPlaceholder] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (focused || value) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const id = window.setInterval(() => {
      setPlaceholder((index) => (index + 1) % PLACEHOLDERS.length);
    }, 4000);
    return () => window.clearInterval(id);
  }, [focused, value]);

  async function submit(text: string) {
    const message = text.trim();
    if (!message || leaving) return;
    setError("");
    setLeaving(true);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) await new Promise((resolve) => window.setTimeout(resolve, 420));
    try {
      const { trip_id } = await getClient().createTrip(message);
      sessionStorage.setItem(TRIP_MESSAGE_KEY, message);
      router.push(`/trip/${trip_id}`);
    } catch (err) {
      setLeaving(false);
      setError(err instanceof Error ? err.message : "Could not start the trip");
    }
  }

  return (
    <div className="home-screen">
      <header className="home-bar">
        <Link href="/" className="home-brand" aria-label="Swanavi home">
          <SwanMark className="h-7 w-7" />
          Swanavi
        </Link>
        <nav className="home-nav" aria-label="Account">
          <Link href="/trips">My trips</Link>
          <Link href="/profile" className="home-profile" aria-label="Profile" />
        </nav>
      </header>
      <main className="home-center">
        <SwanMark className="home-mark" tone="two" />
        <h1 className="home-title">Swanavi</h1>
        <form
          className={leaving ? "home-prompt is-leaving" : "home-prompt"}
          onSubmit={(event) => {
            event.preventDefault();
            void submit(value);
          }}
        >
          <label className="sr-only" htmlFor="trip-prompt">Where do you want to go?</label>
          <input
            id="trip-prompt"
            autoFocus
            value={value}
            placeholder={PLACEHOLDERS[placeholder]}
            onChange={(event) => setValue(event.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
          <button className="home-send" type="submit" disabled={!value.trim()} aria-label="Start the trip">
            ↑
          </button>
        </form>
        <div className="home-chips">
          {CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              className="home-chip"
              onClick={() => {
                setValue(chip);
                document.getElementById("trip-prompt")?.focus();
              }}
            >
              {chip}
            </button>
          ))}
        </div>
        {error ? <p role="alert">{error}</p> : null}
      </main>
    </div>
  );
}
