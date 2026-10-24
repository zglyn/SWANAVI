"use client";

import { useEffect, useRef, useState } from "react";

export interface MapStop {
  id: string;
  lat: number;
  lng: number;
  label: string;
  kind: "stop" | "hotel" | "merchant";
}

interface Arc {
  from: [number, number];
  to: [number, number];
}

export function TripMap({
  stops,
  arcs,
  focus,
  dayLabel,
}: {
  stops: MapStop[];
  arcs: Arc[];
  focus: number;
  dayLabel: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<{ flyTo: (opts: object) => void; jumpTo: (opts: object) => void; remove: () => void; setPitch: (n: number) => void } | null>(null);
  const [fallback, setFallback] = useState(false);
  const [flat, setFlat] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const signature = `${flat}:${focus}:${stops.map((stop) => `${stop.id}:${stop.lat}:${stop.lng}`).join("|")}:${JSON.stringify(arcs)}`;

  useEffect(() => {
    const node = host.current;
    if (!node || fallback) return;
    let cancelled = false;
    let disconnectObserver: (() => void) | undefined;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const drawnStops = stops;
    const drawnArcs = arcs;
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
        });
        map.on("error", () => setFallback(true));
        const fit = () => map.resize();
        const observer = new ResizeObserver(fit);
        observer.observe(node);
        map.on("load", () => {
          fit();
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
          if (drawnStops.length > 1) line("day", drawnStops.map((stop) => [stop.lng, stop.lat]), true);
          drawnStops.forEach((stop, index) => {
            const marker = document.createElement("button");
            marker.type = "button";
            marker.textContent = stop.kind === "hotel" ? "H" : String(index + 1);
            marker.setAttribute("aria-label", stop.label);
            marker.className = stop.kind === "merchant" ? "swan-invert" : "swan-chip";
            marker.style.width = "28px";
            marker.style.height = "28px";
            marker.onclick = () => setActive(stop.id);
            new maplibre.Marker({ element: marker }).setLngLat([stop.lng, stop.lat]).addTo(map);
          });
          const target = drawnStops[Math.min(focus, Math.max(drawnStops.length - 1, 0))];
          if (target) {
            const camera = { center: [target.lng, target.lat] as [number, number], zoom: 13, pitch: reduced || flat ? 0 : 48 };
            if (reduced) map.jumpTo(camera);
            else map.flyTo({ ...camera, essential: true });
          }
        });
        mapRef.current = map;
        disconnectObserver = () => observer.disconnect();
        if (cancelled) disconnectObserver();
      } catch {
        if (!cancelled) setFallback(true);
      }
    })();
    return () => {
      cancelled = true;
      disconnectObserver?.();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [signature, fallback]);

  const selected = stops.find((stop) => stop.id === active);

  if (fallback) {
    return (
      <div className="swan-surface h-full min-h-72 overflow-auto p-4">
        <p className="font-medium">Map unavailable. {dayLabel}</p>
        <ol className="mt-3 space-y-2">
          {stops.map((stop, index) => (
            <li key={stop.id}>
              <button type="button" className="text-left" onClick={() => setActive(stop.id)}>
                {index + 1}. {stop.label}
              </button>
            </li>
          ))}
        </ol>
        {selected ? <p className="mt-3">{selected.label}</p> : null}
      </div>
    );
  }

  return (
    <div className="relative h-full min-h-72">
      <div ref={host} className="swan-map h-full min-h-72 w-full" />
      <button type="button" className="swan-chip absolute top-3 right-3 bg-white" onClick={() => setFlat((value) => !value)}>
        {flat ? "3D view" : "2D view"}
      </button>
      {selected ? <p className="absolute bottom-3 left-3 rounded-full bg-white px-3 py-1 text-sm text-black">{selected.label}</p> : null}
    </div>
  );
}

function greatCircle(from: [number, number], to: [number, number]): [number, number][] {
  const points: [number, number][] = [];
  for (let step = 0; step <= 32; step += 1) {
    const t = step / 32;
    points.push([from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t]);
  }
  return points;
}
