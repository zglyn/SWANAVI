import type { Quote } from "@contracts/api";

export const BOOKING_QUOTES_KEY = "roam.booking";
export const BOOKING_PLAN_KEY = "roam.booking.plan";

const key = (planId: string) => `swan.booked.${planId}`;

export function readBooked(planId: string): string[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem(key(planId));
  return raw ? (JSON.parse(raw) as string[]) : [];
}

export function setBooked(planId: string, item: string, done: boolean): string[] {
  const current = new Set(readBooked(planId));
  if (done) current.add(item);
  else current.delete(item);
  const next = [...current];
  localStorage.setItem(key(planId), JSON.stringify(next));
  return next;
}

export function handOffToWallet(planId: string, quotes: Quote[]) {
  sessionStorage.setItem(BOOKING_QUOTES_KEY, JSON.stringify(quotes));
  sessionStorage.setItem(BOOKING_PLAN_KEY, planId);
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return "the provider";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "the provider";
  }
}
