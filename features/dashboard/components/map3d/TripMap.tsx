"use client";

import { useEffect, useRef, useState } from "react";

export interface MapStop {
  id: string;
  lat: number;
  lng: number;
  label: string;
  kind: "stop" | "hotel" | "merchant";
  badge?: string;
}

interface Arc {
  from: [number, number];
  to: [number, number];
}

type MapHandle = {
  flyTo: (opts: object) => void;
  jumpTo: (opts: object) => void;
  remove: () => void;
  setPitch: (n: number) => void;
};

export function TripMap({
  stops,
  arcs,
  focus,
  dayLabel,
  showToggle = true,
  highlight = null,
  route = true,
  padding,
  onSelect,
}: {
  stops: MapStop[];
  arcs: Arc[];
  focus: number;
  dayLabel: string;
  showToggle?: boolean;
  highlight?: string | null;
  route?: boolean;
  padding?: { top: number; bottom: number; left: number; right: number };
  onSelect?: (id: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapHandle | null>(null);
  const markers = useRef(new Map<string, HTMLElement>());
  const [fallback, setFallback] = useState<string | null>(null);
  const [flat, setFlat] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const signature = `${flat}:${focus}:${route}:${JSON.stringify(padding)}:${stops.map((stop) => `${stop.id}:${stop.lat}:${stop.lng}`).join("|")}:${JSON.stringify(arcs)}`;

  useEffect(() => {
    const node = host.current;
    if (!node || fallback) return;
    if (!hasWebGL()) {
      setFallback("This browser can't draw 3D maps.");
      return;
    }
    let cancelled = false;
    let disconnectObserver: (() => void) | undefined;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const drawnStops = stops;
    const drawnArcs = arcs;
    const inset = padding ?? { top: 72, bottom: 72, left: 72, right: 72 };
    (async () => {
      try {
        const maplibre = await import("maplibre-gl");
        await import("maplibre-gl/dist/maplibre-gl.css");
        if (cancelled || !node) return;
        const ink = getComputedStyle(node).getPropertyValue("--swan-fg").trim() || "black";
        const map = new maplibre.Map({
          container: node,
          style: "https://tiles.openfreemap.org/styles/positron",
          center: drawnStops[0] ? [drawnStops[0].lng, drawnStops[0].lat] : [135.77, 35.01],
          zoom: drawnStops.length ? 11 : 2,
          pitch: reduced || flat ? 0 : 48,
          attributionControl: { compact: true },
        });
        map.on("error", (event) => {
          const detail = event as { sourceId?: string; tile?: unknown; error?: Error };
          if (detail.sourceId || detail.tile) return;
          if (map.loaded()) return;
          setFallback(detail.error?.message || "The map style did not load.");
        });
        map.on("webglcontextlost", () => setFallback("The browser dropped the map's graphics context."));
        const fit = () => map.resize();
        const observer = new ResizeObserver(fit);
        observer.observe(node);
        map.on("load", () => {
          fit();
          addBuildings(map);
          const line = (id: string, coordinates: [number, number][], dashed: boolean) => {
            map.addSource(id, { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } } });
            map.addLayer({
              id,
              type: "line",
              source: id,
              paint: { "line-color": ink, "line-width": 3, "line-dasharray": dashed ? [1.5, 1.5] : [1, 0] },
            });
          };
          drawnArcs.forEach((arc, index) => line(`arc-${index}`, greatCircle(arc.from, arc.to), false));
          const path = drawnStops.filter((stop) => stop.kind === "stop");
          if (route && path.length > 1) line("day", path.map((stop) => [stop.lng, stop.lat]), true);
          let number = 0;
          markers.current.clear();
          drawnStops.forEach((stop) => {
            const marker = document.createElement("button");
            marker.type = "button";
            marker.className = `swan-marker${stop.kind === "stop" && !stop.badge ? "" : " swan-marker-hotel"}`;
            const badge = document.createElement("span");
            badge.className = "swan-marker-badge";
            badge.textContent = stop.badge ?? (stop.kind === "stop" ? String((number += 1)) : "H");
            const text = document.createElement("span");
            text.className = "swan-marker-label";
            text.textContent = stop.label;
            marker.append(badge, text);
            marker.setAttribute("aria-label", stop.label);
            marker.onclick = () => {
              setActive(stop.id);
              onSelect?.(stop.id);
            };
            markers.current.set(stop.id, marker);
            new maplibre.Marker({ element: marker, anchor: "left", offset: [-14, 0] }).setLngLat([stop.lng, stop.lat]).addTo(map);
          });
          const pitch = reduced || flat ? 0 : 48;
          const frame = (points: [number, number][], options: { pitch: number; maxZoom: number }) => {
            const unwrapped = unwrap(points);
            const bounds = unwrapped.reduce((box, point) => box.extend(point), new maplibre.LngLatBounds(unwrapped[0], unwrapped[0]));
            map.fitBounds(bounds, { padding: inset, duration: reduced ? 0 : 1200, essential: true, ...options });
          };
          if (drawnStops.length > 1) {
            frame(drawnStops.map((stop) => [stop.lng, stop.lat]), { pitch, maxZoom: 14 });
          } else if (drawnStops.length === 1) {
            const target = drawnStops[0];
            const camera = { center: [target.lng, target.lat] as [number, number], zoom: 13, pitch, padding: inset };
            if (reduced) map.jumpTo(camera);
            else map.flyTo({ ...camera, essential: true });
          } else if (drawnArcs.length) {
            frame(drawnArcs.flatMap((arc) => [arc.from, arc.to]), { pitch: 0, maxZoom: 6 });
          }
        });
        mapRef.current = map;
        disconnectObserver = () => observer.disconnect();
        if (cancelled) disconnectObserver();
      } catch (err) {
        if (!cancelled) setFallback(err instanceof Error ? err.message : "The map could not start.");
      }
    })();
    return () => {
      cancelled = true;
      disconnectObserver?.();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [signature, fallback]);

  useEffect(() => {
    markers.current.forEach((element, id) => {
      element.classList.toggle("swan-marker-active", id === highlight);
    });
  }, [highlight, signature]);

  const selected = stops.find((stop) => stop.id === active);

  if (fallback) {
    let number = 0;
    return (
      <div className="swan-surface flex h-full min-h-72 flex-col overflow-auto p-5" role="region" aria-label="Route list">
        <p className="swan-eyebrow">Map view is off</p>
        <p className="mt-1 text-xl font-semibold tracking-tight">{dayLabel}</p>
        <p className="swan-muted mt-1 text-sm">{fallback} Here is the route as a list.</p>
        <ol className="mt-4 space-y-2">
          {stops.map((stop) => (
            <li key={stop.id} className="flex items-center gap-3">
              <span className="swan-marker-badge" aria-hidden="true">{stop.badge ?? (stop.kind === "stop" ? (number += 1) : "H")}</span>
              <button type="button" className="text-left" onClick={() => { setActive(stop.id); onSelect?.(stop.id); }}>
                {stop.label}
              </button>
            </li>
          ))}
        </ol>
        {selected ? <p className="mt-3 text-sm">{selected.label}</p> : null}
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-72">
      <div ref={host} className="swan-map h-full min-h-72 w-full" aria-label={`Map of ${dayLabel}`} />
      {showToggle ? (
        <button type="button" className="swan-chip absolute top-3 right-3 bg-white" aria-pressed={flat} onClick={() => setFlat((value) => !value)}>
          {flat ? "3D view" : "2D view"}
        </button>
      ) : null}
      {selected ? <p className="absolute bottom-3 left-3 rounded-full bg-white px-3 py-1 text-sm text-black shadow">{selected.label}</p> : null}
    </div>
  );
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function addBuildings(map: import("maplibre-gl").Map) {
  const style = map.getStyle();
  const source = Object.entries(style.sources).find(([, value]) => value.type === "vector")?.[0];
  if (!source) return;
  const firstSymbol = style.layers.find((layer) => layer.type === "symbol")?.id;
  map.addLayer(
    {
      id: "swan-buildings",
      type: "fill-extrusion",
      source,
      "source-layer": "building",
      minzoom: 13,
      paint: {
        "fill-extrusion-color": "#cfcfcf",
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 12],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.8,
      },
    },
    firstSymbol,
  );
}

function unwrap(points: [number, number][]): [number, number][] {
  if (!points.length) return points;
  let previous = points[0][0];
  return points.map(([lng, lat]) => {
    let value = lng;
    while (value - previous > 180) value -= 360;
    while (previous - value > 180) value += 360;
    previous = value;
    return [value, lat];
  });
}

export function greatCircle(from: [number, number], to: [number, number], steps = 64): [number, number][] {
  const rad = (deg: number) => (deg * Math.PI) / 180;
  const deg = (value: number) => (value * 180) / Math.PI;
  const lon1 = rad(from[0]);
  const lat1 = rad(from[1]);
  const lon2 = rad(to[0]);
  const lat2 = rad(to[1]);
  const d = 2 * Math.asin(Math.sqrt(Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2));
  if (d < 1e-9) return [from, to];
  const points: [number, number][] = [];
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
