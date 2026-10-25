import Link from "next/link";

export default function TripsPage() {
  return (
    <main className="trip-land">
      <div className="trip-land-copy">
        <h1 className="home-title">My trips</h1>
        <p className="swan-muted">No trips yet.</p>
        <p><Link href="/">Start from the prompt</Link></p>
      </div>
    </main>
  );
}
