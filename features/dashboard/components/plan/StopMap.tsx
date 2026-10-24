"use client";

import { useEffect, useRef } from "react";

export interface MapPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
  color: string;
}

export function StopMap({ points }: { points: MapPoint[] }) {
  const node = useRef<HTMLDivElement>(null);
  const latest = useRef(points);
  latest.current = points;
  const key = points.map((point) => `${point.id}:${point.color}:${point.lat}:${point.lng}`).join("|");

  useEffect(() => {
    const host = node.current;
    if (!host) return;
    const drawn = latest.current;
    let map: { remove: () => void } | null = null;
    let cancelled = false;
    (async () => {
      const leaflet = await import("leaflet");
      await import("leaflet/dist/leaflet.css");
      if (cancelled || !host) return;
      const view = leaflet.map(host, { scrollWheelZoom: false });
      leaflet.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
      }).addTo(view);
      const markers = drawn.map((point) =>
        leaflet.circleMarker([point.lat, point.lng], { radius: 8, color: point.color, fillOpacity: 0.9 }).bindTooltip(point.label),
      );
      const group = leaflet.featureGroup(markers).addTo(view);
      if (drawn.length) view.fitBounds(group.getBounds().pad(0.3));
      else view.setView([35.01, 135.77], 11);
      map = view;
    })();
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [key]);

  return <div ref={node} className="h-72 w-full overflow-hidden rounded-2xl border border-line bg-paper-2" />;
}
