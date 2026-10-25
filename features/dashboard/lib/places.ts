export interface PlaceHit {
  label: string;
  lat: number;
  lng: number;
  airports: string[];
}

const AIRPORTS: { code: string; lat: number; lng: number }[] = [
  { code: "SFO", lat: 37.6213, lng: -122.379 },
  { code: "OAK", lat: 37.7126, lng: -122.2197 },
  { code: "SJC", lat: 37.3639, lng: -121.9289 },
  { code: "LAX", lat: 33.9416, lng: -118.4085 },
  { code: "JFK", lat: 40.6413, lng: -73.7781 },
  { code: "LHR", lat: 51.47, lng: -0.4543 },
  { code: "HND", lat: 35.5494, lng: 139.7798 },
  { code: "NRT", lat: 35.772, lng: 140.3929 },
  { code: "KIX", lat: 34.4347, lng: 135.244 },
  { code: "ITM", lat: 34.7855, lng: 135.4382 },
  { code: "CDG", lat: 49.0097, lng: 2.5479 },
];

const CITIES: PlaceHit[] = [
  { label: "San Francisco", lat: 37.7749, lng: -122.4194, airports: ["SFO", "OAK", "SJC"] },
  { label: "Kyoto", lat: 35.0116, lng: 135.7681, airports: ["KIX", "ITM"] },
  { label: "Osaka", lat: 34.6937, lng: 135.5023, airports: ["KIX", "ITM"] },
  { label: "Tokyo", lat: 35.6762, lng: 139.6503, airports: ["HND", "NRT"] },
  { label: "Los Angeles", lat: 34.0522, lng: -118.2437, airports: ["LAX"] },
  { label: "New York", lat: 40.7128, lng: -74.006, airports: ["JFK"] },
  { label: "London", lat: 51.5072, lng: -0.1276, airports: ["LHR"] },
  { label: "Paris", lat: 48.8566, lng: 2.3522, airports: ["CDG"] },
];

function distance(lat: number, lng: number, otherLat: number, otherLng: number) {
  const rad = Math.PI / 180;
  const dLat = (otherLat - lat) * rad;
  const dLng = (otherLng - lng) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat * rad) * Math.cos(otherLat * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function nearestAirports(lat: number, lng: number): string[] {
  return [...AIRPORTS].sort((a, b) => distance(lat, lng, a.lat, a.lng) - distance(lat, lng, b.lat, b.lng)).slice(0, 3).map((item) => item.code);
}

export function matchCity(query: string): PlaceHit | null {
  const needle = query.trim().toLowerCase();
  if (!needle) return null;
  return CITIES.find((city) => city.label.toLowerCase().includes(needle) || needle.includes(city.label.toLowerCase())) ?? null;
}

export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<PlaceHit[]> {
  const needle = query.trim().toLowerCase();
  if (needle.length < 2) return [];
  const local = CITIES.filter((city) => city.label.toLowerCase().includes(needle));
  try {
    const response = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&q=${encodeURIComponent(query)}`, { signal });
    if (!response.ok) return local;
    const rows = await response.json() as { display_name: string; lat: string; lon: string }[];
    const remote = rows.map((row) => {
      const lat = Number(row.lat);
      const lng = Number(row.lon);
      return { label: row.display_name.split(",").slice(0, 3).join(","), lat, lng, airports: nearestAirports(lat, lng) };
    });
    const seen = new Set(local.map((city) => city.label.toLowerCase()));
    return [...local, ...remote.filter((hit) => !seen.has(hit.label.toLowerCase()))].slice(0, 6);
  } catch {
    return local;
  }
}

export async function lookupPlace(query: string): Promise<PlaceHit | null> {
  const local = matchCity(query);
  if (local) return local;
  const hits = await suggestPlaces(query);
  return hits[0] ?? null;
}

export const DESTINATIONS = CITIES.filter((city) => city.label !== "San Francisco");
