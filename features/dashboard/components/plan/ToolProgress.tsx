"use client";

import type { InspectorEvent } from "@contracts/api";

export function ToolProgress({ events, error }: { events: InspectorEvent[]; error?: string | null }) {
  const lines = events.filter((event) => event.type.startsWith("plan."));
  return (
    <ol className="space-y-2">
      {lines.map((event) => (
        <li key={event.id} className="rounded-xl border border-line bg-card px-3 py-2 text-sm">
          {event.message}
        </li>
      ))}
      {error && <li className="rounded-xl bg-torii-soft px-3 py-2 text-sm text-torii">{error}</li>}
    </ol>
  );
}
