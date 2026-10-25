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

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";
const IVORY = "#F6F4EF";
const INK = "#1C1C1A";
const MUTED = "#6E6A62";
const HAIRLINE = "#E4E0D8";
const ACCENT = "#16382E";
const MIST = "rgba(246, 244, 239, 0.72)";
const PITCH = 60;
const BEARING = -20;
const SERIF = 'var(--font-fraunces), "Fraunces", Georgia, serif';
const SANS = 'var(--font-outfit), "Outfit", sans-serif';

type Stage = "frame" | "title" | "map" | "hint" | "sheet";
type Placed = { stop: RouteStop; number: number };

export function QuietScreen({ line }: { line: string }) {
  return (
    <main className="swan-stage">
      <div className="swan-wrap">
        <p className="swan-muted" style={{ marginTop: 72 }}>{line}</p>
      </div>
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
  const missingToken = !token;
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
    map.flyTo({
      center: [stop.lng, stop.lat],
      zoom: 15.5,
      pitch: PITCH,
      bearing: BEARING,
      offset: [0, -70],
      duration: reduced ? 0 : 1400,
      curve: 1,
      essential: true,
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
          zoom: 10.6,
          pitch: PITCH,
          bearing: -32,
          attributionControl: false,
          fadeDuration: 0,
          antialias: true,
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
          dressScene(map);
          paint(map, geometryRef.current, progressRef.current);
          const mark = () => {
            if (!node.isConnected) return;
            const terrain = map?.getTerrain();
            node.dataset.terrain = terrain?.source ?? "";
            node.dataset.exaggeration = String(terrain?.exaggeration ?? "");
            node.dataset.buildings = map?.getLayer("buildings-3d") ? "1" : "0";
            node.dataset.pitch = String(Math.round(map?.getPitch() ?? 0));
            node.dataset.zoom = (map?.getZoom() ?? 0).toFixed(1);
            node.dataset.bearing = String(Math.round(map?.getBearing() ?? 0));
            if ((map?.getZoom() ?? 0) >= 14.2 && map?.getLayer("buildings-3d")) {
              const hits = map.queryRenderedFeatures({ layers: ["buildings-3d"] });
              if (hits.length) node.dataset.buildingHits = String(hits.length);
            }
          };
          mark();
          map.on("move", mark);
          map.on("idle", mark);
          mapReadyRef.current = true;
          setMapReady(true);
          if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            frameRoute(map, placed, 0);
          }
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
      element.style.outline = element.dataset.id === active ? `2px solid ${IVORY}` : "none";
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
    const setAmount = (amount: number) => {
      progressRef.current = amount;
      setProgress(amount);
    };
    const openSheet = () => setStage("sheet");
    const tween = (from: number, to: number, ms: number, done: () => void) => {
      const started = performance.now();
      const tick = (now: number) => {
        if (cancelled) return;
        const raw = Math.min(1, (now - started) / ms);
        setAmount(from + (to - from) * easeCinema(raw));
        if (raw < 1) frames.push(requestAnimationFrame(tick));
        else done();
      };
      frames.push(requestAnimationFrame(tick));
    };
    const play = () => {
      const map = mapRef.current;
      const line = geometryRef.current;
      if (!map || !line || placed.length === 0) {
        later(180, openSheet);
        return;
      }
      const hop = (index: number) => {
        if (cancelled) return;
        if (index >= placed.length) {
          setAmount(1);
          frameRoute(map, placed, 1600);
          later(1600, openSheet);
          return;
        }
        const item = placed[index];
        const prev = placed[index - 1];
        if (!item || item.stop.lat == null || item.stop.lng == null || !prev || prev.stop.lat == null || prev.stop.lng == null) {
          hop(index + 1);
          return;
        }
        const fromT = lineFraction(line, prev.stop.lng, prev.stop.lat);
        const toT = index === placed.length - 1 ? 1 : Math.max(fromT, lineFraction(line, item.stop.lng, item.stop.lat));
        const ms = hopMs(prev.stop, item.stop);
        map.easeTo({
          center: [item.stop.lng, item.stop.lat],
          zoom: 15.4,
          pitch: PITCH,
          bearing: BEARING,
          offset: [0, 40],
          duration: ms,
          easing: easeCinema,
          essential: true,
        });
        tween(fromT, toT, ms, () => {
          setPins(index + 1);
          hop(index + 1);
        });
      };
      const first = placed[0];
      if (!first || first.stop.lat == null || first.stop.lng == null) {
        later(180, openSheet);
        return;
      }
      map.easeTo({
        center: [first.stop.lng, first.stop.lat],
        zoom: 15.4,
        pitch: PITCH,
        bearing: BEARING,
        offset: [0, 40],
        duration: 1700,
        easing: easeCinema,
        essential: true,
      });
      later(1700, () => {
        setPins(1);
        if (placed.length === 1) {
          setAmount(1);
          frameRoute(map, placed, 1600);
          later(1600, openSheet);
          return;
        }
        hop(1);
      });
    };
    const waitToPlay = (shownAt: number) => {
      const watch = () => {
        if (cancelled) return;
        const faded = performance.now() - shownAt >= 800;
        if (mapReadyRef.current && geometryRef.current && faded) {
          play();
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
        waitToPlay(performance.now());
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
        .cine-map .mapboxgl-ctrl-bottom-right { bottom: 28px; }
        .cine-map .mapboxgl-ctrl-attrib { background: rgba(12, 12, 10, 0.55) !important; }
        .cine-map .mapboxgl-ctrl-attrib, .cine-map .mapboxgl-ctrl-attrib a { color: rgba(246, 244, 239, 0.72) !important; }
        .cine-logo.swan-logo { color: ${IVORY}; }
        .cine-sheet-inner { max-width: 1120px; margin: 0 auto; padding: 0 32px 12px; box-sizing: border-box; }
        .cine-book {
          height: 52px;
          margin: 18px 0 8px;
          padding: 0 28px;
          border: 0;
          border-radius: 999px;
          background: ${ACCENT};
          color: ${IVORY};
          font-family: ${SANS};
          font-size: 16px;
          font-weight: 500;
          letter-spacing: 0.01em;
          cursor: pointer;
        }
        @media (max-width: 640px) {
          .cine-sheet-inner { padding: 0 20px 12px; }
          .cine-book { width: 100%; }
        }
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
          background: "#121410",
          pointerEvents: mapOn ? "auto" : "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 28,
          left: 32,
          right: 32,
          zIndex: 2,
          textAlign: "center",
          pointerEvents: "none",
          opacity: titleOn ? 1 : 0,
          transition: motion ?? `opacity 800ms ${EASE}`,
        }}
      >
        <span style={{ display: "flex", justifyContent: "center" }}><SwanLogo className="cine-logo" /></span>
        <h1 style={{ margin: "12px 0 0", fontFamily: SERIF, fontSize: "clamp(48px, 6vw, 76px)", fontWeight: 500, letterSpacing: "-0.045em", lineHeight: 0.96, color: IVORY }}>{city}</h1>
        <p style={{ margin: "8px 0 0", color: MIST, fontFamily: SANS, fontSize: 14, letterSpacing: "0.12em", textTransform: "uppercase" }}>Your trip</p>
      </div>
      {missingToken || mapFailed ? (
        <p
          aria-hidden={!hintOn}
          style={{
            position: "absolute",
            left: 32,
            right: 32,
            top: "34%",
            zIndex: 2,
            margin: 0,
            textAlign: "center",
            color: MIST,
            fontFamily: SANS,
            fontSize: 15,
            letterSpacing: "0.02em",
            opacity: hintOn ? 1 : 0,
            transition: motion ?? `opacity 700ms ${EASE}`,
          }}
        >
          {missingToken ? "A Mapbox token is missing." : "The map didn't load."}
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
          background: IVORY,
          color: INK,
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          transform: stage === "sheet" ? "translateY(0)" : "translateY(110%)",
          transition: motion ?? `transform 800ms ${EASE}`,
          paddingBottom: "env(safe-area-inset-bottom)",
          fontFamily: SANS,
        }}
      >
        <div aria-hidden style={{ width: 36, height: 4, borderRadius: 999, background: HAIRLINE, margin: "10px auto 6px" }} />
        <div className="cine-sheet-inner">
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
                      gridTemplateColumns: "16px 28px 1fr auto",
                      gap: 12,
                      alignItems: "baseline",
                      width: "100%",
                      padding: "14px 0",
                      border: 0,
                      borderBottom: `1px solid ${HAIRLINE}`,
                      background: "transparent",
                      color: selected ? ACCENT : INK,
                      font: "inherit",
                      fontSize: 16,
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <span aria-hidden style={{ width: 8, height: 8, borderRadius: 999, background: selected ? ACCENT : "transparent", transform: "translateY(1px)" }} />
                    <span style={{ color: selected ? ACCENT : MUTED }}>{index + 1}</span>
                    <span>{stop.title}</span>
                    <span style={{ color: MUTED, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase" }}>{stop.kind}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <button type="button" className="cine-book" onClick={onBook}>
            Book Swanavi merchants
          </button>
        </div>
      </section>
    </main>
  );
}

const frameStyle = {
  position: "relative" as const,
  height: "100vh",
  overflow: "hidden",
  background: "#121410",
  color: IVORY,
  fontFamily: SANS,
};

function pinStyle(selected: boolean): Partial<CSSStyleDeclaration> {
  return {
    width: "28px",
    height: "28px",
    borderRadius: "999px",
    border: "0",
    padding: "0",
    background: IVORY,
    color: INK,
    font: `600 12px ${SANS}`,
    lineHeight: "28px",
    textAlign: "center",
    cursor: "pointer",
    opacity: "0",
    outline: selected ? `2px solid ${IVORY}` : "none",
    outlineOffset: "3px",
    boxShadow: "0 6px 16px rgba(0,0,0,0.35)",
    transition: `opacity 320ms ${EASE}`,
  };
}

function dressScene(map: MapboxMap) {
  if (!map.getSource("mapbox-dem")) {
    map.addSource("mapbox-dem", {
      type: "raster-dem",
      url: "mapbox://mapbox.mapbox-terrain-dem-v1",
      tileSize: 512,
      maxzoom: 14,
    });
  }
  map.setTerrain({ source: "mapbox-dem", exaggeration: 1.4 });
  map.setFog({
    range: [0.6, 8],
    color: "#1a1c18",
    "high-color": "#0c1014",
    "horizon-blend": 0.12,
    "space-color": "#07080c",
    "star-intensity": 0.22,
  });
  map.setLight({
    anchor: "viewport",
    color: IVORY,
    intensity: 0.42,
    position: [1.4, 200, 35],
  });
  if (!map.getSource("route")) {
    map.addSource("route", {
      type: "geojson",
      data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [] } },
    });
  }
  const labelId = map.getStyle()?.layers?.find((layer) => layer.type === "symbol" && layer.layout && "text-field" in layer.layout)?.id;
  if (map.getSource("composite") && !map.getLayer("buildings-3d")) {
    map.addLayer({
      id: "buildings-3d",
      source: "composite",
      "source-layer": "building",
      filter: ["==", ["get", "extrude"], "true"],
      type: "fill-extrusion",
      minzoom: 14,
      paint: {
        "fill-extrusion-color": IVORY,
        "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 14, 0, 14.05, ["get", "height"]],
        "fill-extrusion-base": ["interpolate", ["linear"], ["zoom"], 14, 0, 14.05, ["get", "min_height"]],
        "fill-extrusion-opacity": 0.4,
        "fill-extrusion-vertical-gradient": true,
      },
    }, labelId);
  }
  if (!map.getLayer("route")) {
    map.addLayer({
      id: "route",
      type: "line",
      source: "route",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": IVORY, "line-width": 3.5, "line-opacity": 0.95 },
    }, labelId);
  }
}

function frameRoute(map: MapboxMap, placed: Placed[], duration: number) {
  const points = placed.flatMap((item) => (
    item.stop.lng == null || item.stop.lat == null ? [] : [[item.stop.lng, item.stop.lat] as [number, number]]
  ));
  if (points.length === 0) return;
  if (points.length === 1) {
    map.easeTo({
      center: points[0],
      zoom: 15.2,
      pitch: PITCH,
      bearing: BEARING,
      duration,
      easing: easeCinema,
      essential: true,
    });
    return;
  }
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
  map.fitBounds([[west, south], [east, north]], {
    padding: { top: 150, bottom: 260, left: 48, right: 48 },
    pitch: PITCH,
    bearing: BEARING,
    duration,
    maxZoom: 13.8,
    easing: easeCinema,
    essential: true,
  });
}

function hopMs(from: RouteStop, to: RouteStop) {
  const lat = (((from.lat ?? 0) + (to.lat ?? 0)) / 2) * Math.PI / 180;
  const dx = ((to.lng ?? 0) - (from.lng ?? 0)) * Math.cos(lat);
  const dy = (to.lat ?? 0) - (from.lat ?? 0);
  const km = Math.hypot(dx, dy) * 111;
  if (km > 25) return 1700;
  if (km > 4) return 1200;
  return 900;
}

function lineFraction(line: [number, number][], lng: number, lat: number) {
  if (line.length < 2) return 1;
  let total = 0;
  const spans: number[] = [];
  for (let index = 1; index < line.length; index += 1) {
    const span = Math.hypot(line[index][0] - line[index - 1][0], line[index][1] - line[index - 1][1]);
    spans.push(span);
    total += span;
  }
  if (total === 0) return 0;
  let best = Infinity;
  let bestDist = 0;
  let walked = 0;
  for (let index = 0; index < line.length; index += 1) {
    const distance = Math.hypot(line[index][0] - lng, line[index][1] - lat);
    if (distance < best) {
      best = distance;
      bestDist = walked;
    }
    if (index < spans.length) walked += spans[index];
  }
  return bestDist / total;
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
