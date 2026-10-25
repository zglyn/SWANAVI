"use client";

import type { GeoJSONSource, Map as MapboxMap, Marker } from "mapbox-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { SwanLogo } from "@/components/swan/Logo";
import {
  easeCinema,
  routeGeometry,
  sliceLine,
  straightGeometry,
  type RouteLeg,
  type RouteStop,
} from "@/lib/tripRoute";

const FONT = 'system-ui, -apple-system, "SF Pro Display", sans-serif';
const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";
const INK = "rgba(255,255,255,0.62)";
const HAIRLINE = "rgba(255,255,255,0.14)";

type Stage = "frame" | "title" | "map" | "hint" | "sheet";

export function QuietScreen({ line }: { line: string }) {
  return (
    <main style={{ ...frameStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ margin: 0, color: INK, fontSize: 16 }}>{line}</p>
    </main>
  );
}

export function CinematicTrip({
  destination,
  stops,
  legs,
  token,
  onBook,
}: {
  destination: string;
  stops: RouteStop[];
  legs: RouteLeg[];
  token: string;
  onBook: () => void;
}) {
  const city = destination.split(",")[0]?.trim() || destination;
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const mapboxRef = useRef<typeof import("mapbox-gl").default | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const geometryRef = useRef<[number, number][] | null>(null);
  const progressRef = useRef(0);
  const mapReadyRef = useRef(false);
  const focusRef = useRef<(id: string) => void>(() => {});
  const [stage, setStage] = useState<Stage>("frame");
  const [progress, setProgress] = useState(0);
  const [pins, setPins] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapFailed, setMapFailed] = useState(false);
  const [geometryTick, setGeometryTick] = useState(0);
  const [reduced, setReduced] = useState(false);
  const showMap = Boolean(token) && !mapFailed;
  const signature = useMemo(
    () => stops.map((stop) => `${stop.id}:${stop.lat}:${stop.lng}:${stop.kind}`).join("|"),
    [stops],
  );
  const placed = stops.flatMap((stop, index) => (
    stop.lat == null || stop.lng == null ? [] : [{ stop, number: index + 1 }]
  ));

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  focusRef.current = (id: string) => {
    setActive(id);
    const stop = stops.find((item) => item.id === id);
    const map = mapRef.current;
    if (!stop || stop.lat == null || stop.lng == null || !map) return;
    map.easeTo({
      center: [stop.lng, stop.lat],
      zoom: 14,
      offset: [0, -80],
      duration: reduced ? 0 : 900,
      easing: easeCinema,
    });
  };

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      if (cancelled || geometryRef.current) return;
      geometryRef.current = straightGeometry(stops);
      setGeometryTick((value) => value + 1);
    }, 7000);
    routeGeometry(token, stops, legs, controller.signal).then((line) => {
      if (cancelled) return;
      geometryRef.current = line.length > 1 ? line : straightGeometry(stops);
      setGeometryTick((value) => value + 1);
    }).catch(() => {
      if (cancelled) return;
      geometryRef.current = straightGeometry(stops);
      setGeometryTick((value) => value + 1);
    });
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [token, stops, legs]);

  useEffect(() => {
    if (!showMap) return;
    const node = host.current;
    if (!node) return;
    let cancelled = false;
    let map: MapboxMap | null = null;
    let observer: ResizeObserver | null = null;
    mapReadyRef.current = false;
    setMapReady(false);
    (async () => {
      try {
        const loaded = await import("mapbox-gl");
        await import("mapbox-gl/dist/mapbox-gl.css");
        if (cancelled || !node) return;
        const mapboxgl = loaded.default ?? loaded;
        mapboxRef.current = mapboxgl;
        mapboxgl.accessToken = token;
        const first = placed[0]?.stop;
        map = new mapboxgl.Map({
          container: node,
          style: "mapbox://styles/mapbox/dark-v11",
          center: first?.lng != null && first.lat != null ? [first.lng, first.lat] : [135.7681, 35.0116],
          zoom: 11,
          attributionControl: false,
          fadeDuration: 0,
          pitch: 0,
          bearing: 0,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
        });
        map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-right");
        map.touchPitch.disable();
        map.dragRotate.disable();
        map.on("error", (event) => {
          const message = String(event.error?.message ?? "");
          if (/token|unauthorized|forbidden|401|403/i.test(message)) setMapFailed(true);
        });
        map.on("load", () => {
          if (cancelled || !map) return;
          if (!map.getSource("route")) {
            map.addSource("route", {
              type: "geojson",
              data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [] } },
            });
            map.addLayer({
              id: "route",
              type: "line",
              source: "route",
              layout: { "line-cap": "round", "line-join": "round" },
              paint: { "line-color": "#ffffff", "line-width": 2.5, "line-opacity": 0.95 },
            });
          }
          fitPoints(map, placed.map((item) => [item.stop.lng as number, item.stop.lat as number]));
          paint(map, geometryRef.current, progressRef.current);
          mapReadyRef.current = true;
          setMapReady(true);
        });
        observer = new ResizeObserver(() => map?.resize());
        observer.observe(node);
        mapRef.current = map;
      } catch {
        if (!cancelled) setMapFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      observer?.disconnect();
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map?.remove();
      if (mapRef.current === map) mapRef.current = null;
      mapReadyRef.current = false;
      setMapReady(false);
    };
  }, [showMap, token, signature]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !geometryTick) return;
    if (progressRef.current > 0) paint(map, geometryRef.current, progressRef.current);
  }, [geometryTick, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    paint(map, geometryRef.current, progress);
  }, [progress, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const mapboxgl = mapboxRef.current;
    if (!mapReady || !map || !mapboxgl || !showMap) return;
    while (markersRef.current.length < pins) {
      const index = markersRef.current.length;
      const item = placed[index];
      if (!item || item.stop.lat == null || item.stop.lng == null) break;
      const element = document.createElement("button");
      element.type = "button";
      element.dataset.id = item.stop.id;
      element.textContent = String(item.number);
      element.setAttribute("aria-label", `${item.number}. ${item.stop.title}`);
      Object.assign(element.style, pinStyle(false));
      element.onclick = () => focusRef.current(item.stop.id);
      const seen = placed.slice(0, index).filter((other) => (
        Math.abs((other.stop.lat ?? 0) - (item.stop.lat ?? 0)) < 0.0002
        && Math.abs((other.stop.lng ?? 0) - (item.stop.lng ?? 0)) < 0.0002
      )).length;
      const marker = new mapboxgl.Marker({ element, offset: [seen * 16, seen * -14] })
        .setLngLat([item.stop.lng, item.stop.lat])
        .addTo(map);
      markersRef.current.push(marker);
      requestAnimationFrame(() => {
        element.style.opacity = "1";
      });
    }
  }, [pins, mapReady, showMap, signature]);

  useEffect(() => {
    for (const marker of markersRef.current) {
      const element = marker.getElement();
      element.style.outline = element.dataset.id === active ? "2px solid #ffffff" : "none";
      element.style.outlineOffset = "3px";
    }
  }, [active, pins]);

  useEffect(() => {
    let cancelled = false;
    const timers: number[] = [];
    const frames: number[] = [];
    const later = (ms: number, run: () => void) => {
      timers.push(window.setTimeout(() => {
        if (!cancelled) run();
      }, ms));
    };
    const openSheet = () => setStage("sheet");
    const revealPins = () => {
      const total = placed.length;
      if (total === 0) {
        later(180, openSheet);
        return;
      }
      let count = 0;
      const step = () => {
        if (cancelled) return;
        count += 1;
        setPins(count);
        if (count < total) later(90, step);
        else later(220, openSheet);
      };
      step();
    };
    const drawLine = () => {
      const map = mapRef.current;
      const line = geometryRef.current;
      if (map && line && line.length > 1) fitPoints(map, line);
      const started = performance.now();
      const tick = (now: number) => {
        if (cancelled) return;
        const raw = Math.min(1, (now - started) / 1200);
        const eased = easeCinema(raw);
        progressRef.current = eased;
        setProgress(eased);
        if (raw < 1) frames.push(requestAnimationFrame(tick));
        else revealPins();
      };
      frames.push(requestAnimationFrame(tick));
    };
    const waitToDraw = (shownAt: number) => {
      const watch = () => {
        if (cancelled) return;
        const faded = performance.now() - shownAt >= 800;
        if (mapReadyRef.current && geometryRef.current && faded) {
          drawLine();
          return;
        }
        frames.push(requestAnimationFrame(watch));
      };
      frames.push(requestAnimationFrame(watch));
    };

    if (reduced) {
      progressRef.current = 1;
      setProgress(1);
      setPins(placed.length);
      setStage("sheet");
      return () => {
        cancelled = true;
      };
    }

    later(280, () => setStage("title"));
    if (!showMap) {
      later(1100, () => setStage("hint"));
      later(1680, openSheet);
    } else {
      later(1100, () => {
        setStage("map");
        waitToDraw(performance.now());
      });
    }

    return () => {
      cancelled = true;
      timers.forEach((id) => window.clearTimeout(id));
      frames.forEach((id) => window.cancelAnimationFrame(id));
    };
  }, [showMap, reduced, signature]);

  const titleOn = stage !== "frame";
  const mapOn = showMap && (stage === "map" || stage === "sheet");
  const hintOn = !showMap && (stage === "hint" || stage === "sheet");
  const motion = reduced ? "none" : undefined;

  return (
    <main style={frameStyle} data-map={showMap ? "mapbox" : "off"}>
      <style>{`
        .cine-map .mapboxgl-ctrl-bottom-left,
        .cine-map .mapboxgl-ctrl-bottom-right { bottom: 248px; }
        .cine-map .mapboxgl-ctrl-attrib { background: rgba(0,0,0,0.55) !important; }
        .cine-map .mapboxgl-ctrl-attrib, .cine-map .mapboxgl-ctrl-attrib a { color: rgba(255,255,255,0.62) !important; }
      `}</style>
      <div
        ref={host}
        className="cine-map"
        aria-hidden={!showMap}
        style={{
          position: "absolute",
          inset: 0,
          opacity: mapOn ? 1 : 0,
          transition: motion ?? `opacity 800ms ${EASE}`,
          background: "#000000",
          pointerEvents: mapOn ? "auto" : "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 36,
          left: 24,
          right: 24,
          zIndex: 2,
          textAlign: "center",
          pointerEvents: "none",
          opacity: titleOn ? 1 : 0,
          transition: motion ?? `opacity 800ms ${EASE}`,
        }}
      >
        <span style={{ display: "flex", justifyContent: "center" }}><SwanLogo /></span>
        <h1 style={{ margin: "14px 0 0", fontSize: 44, fontWeight: 500, letterSpacing: "-0.04em", lineHeight: 1 }}>{city}</h1>
        <p style={{ margin: "8px 0 0", color: INK, fontSize: 16 }}>Your trip</p>
      </div>
      {!showMap ? (
        <p
          aria-hidden={!hintOn}
          style={{
            position: "absolute",
            left: 32,
            right: 32,
            top: 220,
            zIndex: 2,
            margin: 0,
            textAlign: "center",
            color: INK,
            fontSize: 16,
            opacity: hintOn ? 1 : 0,
            transition: motion ?? `opacity 700ms ${EASE}`,
          }}
        >
          Add your Mapbox token to see the map.
        </p>
      ) : null}
      <section
        aria-label="Itinerary"
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 3,
          maxHeight: "min(520px, 58vh)",
          overflowY: "auto",
          background: "#0C0C0C",
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          boxShadow: `inset 0 1px 0 ${HAIRLINE}`,
          transform: stage === "sheet" ? "translateY(0)" : "translateY(110%)",
          transition: motion ?? `transform 800ms ${EASE}`,
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        <div aria-hidden style={{ width: 36, height: 4, borderRadius: 999, background: HAIRLINE, margin: "10px auto 6px" }} />
        <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {stops.map((stop, index) => {
            const selected = active === stop.id;
            return (
              <li key={`${stop.id}-${index}`}>
                <button
                  type="button"
                  onClick={() => focusRef.current(stop.id)}
                  aria-current={selected ? "true" : undefined}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "28px 1fr auto",
                    gap: 12,
                    alignItems: "baseline",
                    width: "100%",
                    padding: "14px 20px",
                    border: 0,
                    borderBottom: `1px solid ${HAIRLINE}`,
                    background: selected ? "rgba(255,255,255,0.06)" : "transparent",
                    color: "#ffffff",
                    font: "inherit",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <span style={{ color: INK }}>{index + 1}</span>
                  <span>{stop.title}</span>
                  <span style={{ color: INK, fontSize: 13 }}>{stop.kind}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <button
          type="button"
          onClick={onBook}
          style={{
            display: "block",
            margin: "16px 20px 20px",
            width: "calc(100% - 40px)",
            height: 48,
            border: 0,
            borderRadius: 999,
            background: "#ffffff",
            color: "#000000",
            font: `600 15px ${FONT}`,
            cursor: "pointer",
          }}
        >
          Book Swanavi merchants
        </button>
      </section>
    </main>
  );
}

const frameStyle = {
  position: "relative" as const,
  height: "100vh",
  overflow: "hidden",
  background: "#000000",
  color: "#ffffff",
  fontFamily: FONT,
};

function pinStyle(selected: boolean): Partial<CSSStyleDeclaration> {
  return {
    width: "28px",
    height: "28px",
    borderRadius: "999px",
    border: "0",
    padding: "0",
    background: "#ffffff",
    color: "#000000",
    font: '600 12px system-ui, -apple-system, "SF Pro Display", sans-serif',
    lineHeight: "28px",
    textAlign: "center",
    cursor: "pointer",
    opacity: "0",
    outline: selected ? "2px solid #ffffff" : "none",
    outlineOffset: "3px",
    transition: "opacity 320ms cubic-bezier(0.22, 1, 0.36, 1)",
  };
}

function fitPoints(map: MapboxMap, points: [number, number][]) {
  if (points.length === 0) return;
  let west = points[0][0];
  let east = points[0][0];
  let south = points[0][1];
  let north = points[0][1];
  for (const [lng, lat] of points) {
    west = Math.min(west, lng);
    east = Math.max(east, lng);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  if (west === east && south === north) {
    map.jumpTo({ center: [west, south], zoom: 13 });
    return;
  }
  map.fitBounds([[west, south], [east, north]], {
    padding: { top: 168, bottom: 260, left: 36, right: 36 },
    duration: 0,
    maxZoom: 13.5,
    linear: true,
  });
}

function paint(map: MapboxMap, line: [number, number][] | null, amount: number) {
  if (!line || !map.isStyleLoaded() || !map.getSource("route")) return;
  const source = map.getSource("route") as GeoJSONSource;
  source.setData({
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: sliceLine(line, amount) },
  });
}
