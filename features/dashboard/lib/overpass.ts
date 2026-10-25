import type { Candidate } from "@contracts/api";

const OVERPASS = "https://overpass-api.de/api/interpreter";

function categoryOf(tags: Record<string, string>): string {
  if (tags.amenity === "place_of_worship") return "temples";
  if (tags.tourism === "museum") return "museums";
  if (tags.tourism === "viewpoint" || tags.leisure === "park") return "nature";
  if (tags.amenity === "restaurant" || tags.amenity === "cafe") return "food";
  return tags.tourism || "attraction";
}

/** Browser-side Overpass fallback when the gateway has not supplied candidates. */
export async function fetchOsmAttractions(place: string, interests: string[], signal?: AbortSignal): Promise<Candidate[]> {
  const city = place.split(",")[0]?.trim() || place;
  const filters: string[] = [];
  if (!interests.length || interests.includes("temples")) filters.push('nwr["amenity"="place_of_worship"]["name"]');
  if (!interests.length || interests.includes("museums")) filters.push('nwr["tourism"="museum"]["name"]');
  if (!interests.length || interests.includes("nature")) {
    filters.push('nwr["tourism"="viewpoint"]["name"]');
    filters.push('nwr["leisure"="park"]["name"]');
  }
  if (!interests.length || interests.includes("food")) filters.push('nwr["amenity"="restaurant"]["name"]');
  if (!filters.length) filters.push('nwr["tourism"="attraction"]["name"]');
  const body = filters.map((item) => `${item}(area.search);`).join("");
  const query = `[out:json][timeout:25];area[name="${city}"]->.search;(${body});out center 30;`;
  const response = await fetch(OVERPASS, {
    method: "POST",
    body: new URLSearchParams({ data: query }),
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    signal,
  });
  if (!response.ok) throw new Error(`Overpass ${response.status}`);
  const payload = (await response.json()) as { elements?: Array<Record<string, unknown>> };
  const candidates: Candidate[] = [];
  for (const element of payload.elements ?? []) {
    const tags = (element.tags || {}) as Record<string, string>;
    const center = (element.center || {}) as { lat?: number; lon?: number };
    const lat = (element.lat as number | undefined) ?? center.lat;
    const lng = (element.lon as number | undefined) ?? center.lon;
    if (!tags.name || lat == null || lng == null) continue;
    const category = categoryOf(tags);
    candidates.push({
      id: `osm-${element.id}`,
      kind: "attraction",
      attraction: {
        id: `osm-${element.id}`,
        name: tags.name,
        category,
        location: { lat, lng },
        area: city,
        description: tags.description || tags.tourism || tags.amenity || "OpenStreetMap place",
        image_url: null,
        popularity: 0.45,
        typical_duration_min: 45,
        opening_hours: tags.opening_hours ?? null,
        free: true,
        source: "osm",
      },
    });
  }
  return candidates;
}
