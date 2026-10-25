import type { BookingChannel, BookingLine, Proposal, Quote, Suggestion } from "@contracts/api";

export interface BookingGroups {
  wallet: Suggestion[];
  external: Suggestion[];
  free: Suggestion[];
  waiting: Suggestion[];
}

export function channelOf(row: Suggestion): BookingChannel | null {
  if (quoteOf(row)) return "wallet";
  if (row.kind === "flight" || row.kind === "hotel") return "external";
  return row.item.attraction && !row.item.attraction.free ? "external" : null;
}

export function quoteOf(row: Suggestion): Quote | null {
  if (row.kind === "flight") return null;
  if (row.kind === "hotel") return row.item.offer.quote ?? null;
  return row.item.quote ?? null;
}

export function linkOf(row: Suggestion): string | null {
  if (row.kind === "flight") return row.item.deep_link ?? null;
  if (row.kind === "hotel") return row.item.offer.deep_link ?? null;
  return null;
}

export function groupForBooking(proposal: Proposal): BookingGroups {
  const groups: BookingGroups = { wallet: [], external: [], free: [], waiting: [] };
  for (const row of proposal.suggestions) {
    if (row.status === "rejected") continue;
    if (row.status !== "accepted" && row.status !== "booked") {
      groups.waiting.push(row);
      continue;
    }
    const channel = channelOf(row);
    groups[channel ?? "free"].push(row);
  }
  return groups;
}

export function withBookings(proposal: Proposal, lines: BookingLine[]): Proposal {
  const booked = new Set(lines.filter((line) => line.status === "booked").map((line) => line.suggestion_id));
  if (!booked.size) return proposal;
  return {
    ...proposal,
    suggestions: proposal.suggestions.map((row) => (booked.has(row.id) ? { ...row, status: "booked" } : row)),
  };
}

export function mergeLines(current: BookingLine[], next: BookingLine[]): BookingLine[] {
  const byId = new Map(current.map((line) => [line.suggestion_id, line]));
  next.forEach((line) => byId.set(line.suggestion_id, line));
  return [...byId.values()];
}
