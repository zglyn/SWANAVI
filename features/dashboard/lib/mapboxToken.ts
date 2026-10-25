/** Public Mapbox token only. Empty, or any secret sk. token, stays unused. */
export function mapboxPublicToken(): string {
  // Static reads so Next inlines the public value. The secrets manager and .env use the first name.
  const token = (process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "").trim();
  if (!token.startsWith("pk.")) return "";
  return token;
}
