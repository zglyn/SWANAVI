/** Public Mapbox token only. Empty, or any secret sk. token, stays unused. */
export function mapboxPublicToken(): string {
  const token = (process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "").trim();
  if (!token.startsWith("pk.")) return "";
  return token;
}
