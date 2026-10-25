// Pure trip picture. No DOM, no GL. TripMap and the controller both read this.

export interface MapStop {
  id: string;
  lat: number;
  lng: number;
  label: string;
  kind: "stop" | "hotel" | "merchant";
  badge?: string;
}

export type LngLat = [lng: number, lat: number];

export interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export type Dimension = "2d" | "3d";

export interface SceneArc {
  from: LngLat;
  to: LngLat;
}

export interface SceneInput {
  stops: readonly MapStop[];
  arcs: readonly SceneArc[];
  focus: number;
  route: boolean;
  highlight: string | null;
  padding: Insets | undefined;
  selectedId: string | null;
  dimension: Dimension;
  reducedMotion: boolean;
}

export interface SceneStop {
  id: string;
  at: LngLat;
  label: string;
  /** Caller badge, else the ordinal among unbadged day stops, else "H". */
  glyph: string;
  /** Numbered day stops are solid. Hotels, merchants, and badged stops are outline. */
  tone: "solid" | "outline";
}

export type RouteRole = "flight" | "day";

export interface RouteFeature {
  type: "Feature";
  properties: { role: RouteRole };
  geometry: { type: "LineString"; coordinates: LngLat[] };
}

export interface Routes {
  type: "FeatureCollection";
  features: RouteFeature[];
}

/** Never an empty bounds box. fitBounds always receives two real corners. */
export type Frame =
  | { kind: "fit"; bounds: [sw: LngLat, ne: LngLat]; scale: "street" | "region" }
  | { kind: "point"; at: LngLat }
  | { kind: "world" };

export interface TripScene {
  stops: SceneStop[];
  /** Changes when a stop id, position, label, glyph, or tone changes. */
  stopsKey: string;
  routes: Routes;
  /** Built from arc endpoints and day-stop ids, not from the sampled arc. */
  routesKey: string;
  frame: Frame;
  /** Changes when the frame geometry or the padding changes. Hover, selection, and focus do not. */
  frameKey: string;
  padding: Insets;
  /** 48 only for a 3D street frame. Region and world frames stay flat. */
  pitch: 0 | 48;
  /** The caller's stop at `focus`, when that stop survived validation. */
  focusId: string | null;
  /** highlight, else selectedId, when that id is still on the map. */
  activeId: string | null;
  selected: SceneStop | null;
  motion: "animate" | "instant";
}

export const DEFAULT_PADDING: Insets = { top: 72, right: 72, bottom: 72, left: 72 };

/** Room inside each padding band for a 44px control plus a gap. */
export const CHROME_BAND = 56;

const REGION_KM = 150;

export function deriveScene(input: SceneInput): TripScene {
  const { stops, dayIds } = sceneStops(input.stops);
  const kept = new Set(stops.map((stop) => stop.id));
  const arcs = input.arcs.filter((arc) => finitePair(arc.from) && finitePair(arc.to));
  const day = stops.filter((stop) => dayIds.has(stop.id));
  const routes = buildRoutes(arcs, day, input.route);
  const frame = frameFor(stops, arcs);
  const padding = {
    top: input.padding?.top ?? DEFAULT_PADDING.top,
    right: input.padding?.right ?? DEFAULT_PADDING.right,
    bottom: input.padding?.bottom ?? DEFAULT_PADDING.bottom,
    left: input.padding?.left ?? DEFAULT_PADDING.left,
  };
  const pitch: 0 | 48 = input.dimension === "3d" && frame.kind === "fit" && frame.scale === "street" ? 48 : 0;
  const focusTarget = input.stops[input.focus];
  const focusId = focusTarget && kept.has(focusTarget.id) ? focusTarget.id : null;
  const selected = stops.find((stop) => stop.id === input.selectedId) ?? null;
  const activeCandidate = input.highlight ?? input.selectedId;
  const activeId = activeCandidate && kept.has(activeCandidate) ? activeCandidate : null;
  return {
    stops,
    stopsKey: JSON.stringify(stops.map((stop) => [stop.id, round(stop.at[0]), round(stop.at[1]), stop.label, stop.glyph, stop.tone])),
    routes,
    routesKey: JSON.stringify({
      arcs: arcs.map((arc) => [round(arc.from[0]), round(arc.from[1]), round(arc.to[0]), round(arc.to[1])]),
      day: input.route ? day.map((stop) => stop.id) : [],
    }),
    frame,
    frameKey: JSON.stringify({ frame: frameKey(frame), padding }),
    padding,
    pitch,
    focusId,
    activeId,
    selected,
    motion: input.reducedMotion ? "instant" : "animate",
  };
}

/** Chrome sits inside the camera padding, at least 12px from the map edge. */
export function chromeInsets(padding: Insets): Insets {
  const band = (side: number) => Math.max(12, side - CHROME_BAND);
  return { top: band(padding.top), right: band(padding.right), bottom: band(padding.bottom), left: band(padding.left) };
}

export function greatCircle(from: LngLat, to: LngLat, steps = 64): LngLat[] {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const deg = (value: number) => (value * 180) / Math.PI;
  const lon1 = rad(from[0]);
  const lat1 = rad(from[1]);
  const lon2 = rad(to[0]);
  const lat2 = rad(to[1]);
  const d = 2 * Math.asin(Math.sqrt(Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2));
  if (d < 1e-9) return [from, to];
  const points: LngLat[] = [];
  let previous = from[0];
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    const a = Math.sin((1 - t) * d) / Math.sin(d);
    const b = Math.sin(t * d) / Math.sin(d);
    const x = a * Math.cos(lat1) * Math.cos(lon1) + b * Math.cos(lat2) * Math.cos(lon2);
    const y = a * Math.cos(lat1) * Math.sin(lon1) + b * Math.cos(lat2) * Math.sin(lon2);
    const z = a * Math.sin(lat1) + b * Math.sin(lat2);
    let lon = deg(Math.atan2(y, x));
    while (lon - previous > 180) lon -= 360;
    while (previous - lon > 180) lon += 360;
    previous = lon;
    points.push([lon, deg(Math.atan2(z, Math.sqrt(x * x + y * y)))]);
  }
  return points;
}

function sceneStops(input: readonly MapStop[]): { stops: SceneStop[]; dayIds: Set<string> } {
  const seen = new Set<string>();
  const dayIds = new Set<string>();
  const stops: SceneStop[] = [];
  let ordinal = 0;
  for (const stop of input) {
    if (!Number.isFinite(stop.lat) || !Number.isFinite(stop.lng)) continue;
    if (seen.has(stop.id)) continue;
    seen.add(stop.id);
    const numbered = stop.kind === "stop" && !stop.badge;
    if (numbered) ordinal += 1;
    // The day line follows kind "stop", including badged lodging. Hotels stay off it.
    if (stop.kind === "stop") dayIds.add(stop.id);
    stops.push({
      id: stop.id,
      at: [stop.lng, stop.lat],
      label: stop.label,
      glyph: stop.badge ?? (stop.kind === "stop" ? String(ordinal) : "H"),
      tone: numbered ? "solid" : "outline",
    });
  }
  return { stops, dayIds };
}

function buildRoutes(arcs: readonly SceneArc[], day: readonly SceneStop[], route: boolean): Routes {
  const features: RouteFeature[] = arcs.map((arc) => ({
    type: "Feature",
    properties: { role: "flight" },
    geometry: { type: "LineString", coordinates: greatCircle(arc.from, arc.to) },
  }));
  if (route && day.length > 1) {
    features.push({
      type: "Feature",
      properties: { role: "day" },
      geometry: { type: "LineString", coordinates: unwrap(day.map((stop) => stop.at)) },
    });
  }
  return { type: "FeatureCollection", features };
}

function frameFor(stops: readonly SceneStop[], arcs: readonly SceneArc[]): Frame {
  if (stops.length === 1) return { kind: "point", at: stops[0].at };
  if (stops.length === 0 && arcs.length === 0) return { kind: "world" };
  const stopPoints = stops.map((stop) => stop.at);
  const base = stopPoints.length > 0 ? stopPoints : arcs.flatMap((arc) => greatCircle(arc.from, arc.to));
  const unwrapped = unwrap(base);
  let bounds = boundsOf(unwrapped);
  const scale = spanKm(bounds) > REGION_KM ? "region" : "street";
  // A street frame stays on the day. A region frame has to include the arc or a long-haul bow is clipped.
  if (scale === "region" && stopPoints.length > 0 && arcs.length > 0) {
    const origin = (bounds[0][0] + bounds[1][0]) / 2;
    const extra = arcs.flatMap((arc) => greatCircle(arc.from, arc.to).map((point) => alignLng(point, origin)));
    bounds = boundsOf([...unwrapped, ...extra]);
  }
  return { kind: "fit", bounds, scale };
}

function frameKey(frame: Frame): unknown {
  if (frame.kind === "world") return "world";
  if (frame.kind === "point") return ["point", round(frame.at[0]), round(frame.at[1])];
  const [sw, ne] = frame.bounds;
  return ["fit", frame.scale, round(sw[0]), round(sw[1]), round(ne[0]), round(ne[1])];
}

function unwrap(points: readonly LngLat[]): LngLat[] {
  if (!points.length) return [];
  let previous = points[0][0];
  return points.map(([lng, lat]) => {
    let value = lng;
    while (value - previous > 180) value -= 360;
    while (previous - value > 180) value += 360;
    previous = value;
    return [value, lat];
  });
}

function alignLng(point: LngLat, originLng: number): LngLat {
  let lng = point[0];
  while (lng - originLng > 180) lng -= 360;
  while (originLng - lng > 180) lng += 360;
  return [lng, point[1]];
}

function boundsOf(points: readonly LngLat[]): [LngLat, LngLat] {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const [lng, lat] of points) {
    minLng = Math.min(minLng, lng);
    minLat = Math.min(minLat, lat);
    maxLng = Math.max(maxLng, lng);
    maxLat = Math.max(maxLat, lat);
  }
  return [[minLng, minLat], [maxLng, maxLat]];
}

function spanKm(bounds: [LngLat, LngLat]): number {
  const [sw, ne] = bounds;
  return Math.max(haversineKm([sw[0], sw[1]], [ne[0], sw[1]]), haversineKm([sw[0], sw[1]], [sw[0], ne[1]]));
}

function haversineKm(a: LngLat, b: LngLat): number {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = rad(b[1] - a[1]);
  const dLng = rad(b[0] - a[0]);
  const lat1 = rad(a[1]);
  const lat2 = rad(b[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function finitePair(point: LngLat): boolean {
  return Number.isFinite(point[0]) && Number.isFinite(point[1]);
}

function round(value: number): number {
  return Number(value.toFixed(5));
}
