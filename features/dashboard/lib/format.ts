export const fmt = (v: string | number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(digits);

export const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Tokyo" });

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const short = (hash: string) => `${hash.slice(0, 6)}…${hash.slice(-4)}`;
