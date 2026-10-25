"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TRIP_MESSAGE_KEY } from "@/lib/tripDraft";

export default function TripPage() {
  const params = useParams<{ id: string }>();
  const [message, setMessage] = useState("");

  useEffect(() => {
    setMessage(sessionStorage.getItem(TRIP_MESSAGE_KEY) ?? "");
  }, []);

  return (
    <main className="trip-land">
      <header className="home-bar">
        <Link href="/" className="home-brand">Swanavi</Link>
      </header>
      <div className="trip-land-copy">
        <p className="swan-muted">Trip {params.id}</p>
        {message ? <p>{message}</p> : <p className="swan-muted">This trip has no opening message on this browser.</p>}
      </div>
      <form className="home-prompt home-prompt-docked" onSubmit={(event) => event.preventDefault()}>
        <label className="sr-only" htmlFor="trip-reply">Reply</label>
        <input id="trip-reply" placeholder="Reply…" />
        <button className="home-send" type="submit" aria-label="Send">↑</button>
      </form>
    </main>
  );
}
