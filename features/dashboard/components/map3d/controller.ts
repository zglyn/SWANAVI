import { basemap, type GlMarker, type GlSurface, type RouteLayer } from "./basemap";
import type { Frame, Insets, LngLat, RouteRole, SceneStop, TripScene } from "./scene";

export type MapFailure = "no-webgl" | "style" | "context-lost" | "engine";

export interface ControllerEvents {
  ready(): void;
  stopPressed(id: string): void;
  failed(failure: MapFailure, detail?: string): void;
}

export interface TripMapController {
  apply(scene: TripScene): void;
  refit(): void;
  zoomBy(step: 1 | -1): void;
  destroy(): void;
}

type State =
  | { phase: "sizing"; latest: TripScene; observer: ResizeObserver }
  | {
      phase: "opening";
      latest: TripScene;
      abort: AbortController;
      observer: ResizeObserver;
      surface: GlSurface | null;
    }
  | {
      phase: "ready";
      surface: GlSurface;
      latest: TripScene;
      applied: Applied;
      markers: Map<string, MarkerEntry>;
      observer: ResizeObserver;
    }
  | { phase: "dead" };

interface Applied {
  stopsKey: string;
  routesKey: string;
  frameKey: string;
  geometryKey: string;
  pitch: 0 | 48;
  focusId: string | null;
  activeId: string | null;
}

interface MarkerEntry {
  element: HTMLButtonElement;
  handle: GlMarker;
  drawn: SceneStop;
}

const ROUTE_SOURCE = "swan-routes";
const ANIMATED_MS = 900;

const ROUTE_STYLE: Record<RouteRole, { width: number; casing: number; dash?: [number, number] }> = {
  flight: { width: 2.5, casing: 6 },
  day: { width: 3, casing: 7, dash: [2, 1.5] },
};

const BLANK: Applied = {
  stopsKey: "",
  routesKey: "",
  frameKey: "",
  geometryKey: "",
  pitch: 0,
  focusId: null,
  activeId: null,
};

export function createTripMapController(host: HTMLElement, first: TripScene, events: ControllerEvents): TripMapController {
  let state: State = { phase: "dead" };

  const observer = new ResizeObserver(() => onResize());

  function onResize() {
    if (state.phase === "dead" || state.phase === "opening") return;
    const { width, height } = host.getBoundingClientRect();
    if (width <= 0 || height <= 0) return;
    if (state.phase === "sizing") {
      void beginOpen();
      return;
    }
    state.surface.map.resize();
  }

  function fail(failure: MapFailure, detail?: string) {
    if (state.phase === "dead") return;
    destroy();
    events.failed(failure, detail);
  }

  async function beginOpen() {
    if (state.phase !== "sizing") return;
    const abort = new AbortController();
    const resize = state.observer;
    state = { phase: "opening", latest: state.latest, abort, observer: resize, surface: null };
    let surface: GlSurface | null = null;
    try {
      surface = await basemap.open(host, startCamera(state.latest), abort.signal);
    } catch (err) {
      if (abort.signal.aborted || state.phase !== "opening") return;
      fail("engine", err instanceof Error ? err.message : undefined);
      return;
    }
    if (state.phase !== "opening") {
      surface?.map.remove();
      return;
    }
    state = { ...state, surface };
    if (abort.signal.aborted) {
      destroy();
      return;
    }
    if (!surface) {
      fail("engine");
      return;
    }
    performance.mark("swan-map:open");
    const map = surface.map;
    map.on("error", (event) => {
      if (state.phase !== "opening") return;
      const detail = readError(event);
      if (detail.sourceId || detail.tile) return;
      fail("style", detail.message);
    });
    map.on("webglcontextlost", () => {
      if (state.phase === "dead") return;
      fail("context-lost");
    });
    const onStyle = () => {
      if (state.phase !== "opening") return;
      const ink = readInk(host);
      try {
        addRoutes(surface, state.latest, ink.ink, ink.paper);
        map.resize();
        state = {
          phase: "ready",
          surface,
          latest: state.latest,
          applied: BLANK,
          markers: new Map(),
          observer: resize,
        };
        applyNow(true);
        events.ready();
      } catch (err) {
        fail("style", err instanceof Error ? err.message : undefined);
      }
    };
    map.on("style.load", onStyle);
    if (map.isStyleLoaded()) onStyle();
  }

  function apply(scene: TripScene) {
    if (state.phase === "dead") return;
    state.latest = scene;
    if (state.phase === "ready") applyNow(false);
  }

  function applyNow(firstFrame: boolean) {
    if (state.phase !== "ready") return;
    const scene = state.latest;
    const applied = state.applied;
    const geometryKey = frameGeometryKey(scene.frame);
    const stopsChanged = firstFrame || applied.stopsKey !== scene.stopsKey;
    const routesChanged = firstFrame || applied.routesKey !== scene.routesKey;
    const frameChanged = firstFrame || applied.frameKey !== scene.frameKey;
    const paddingOnly = frameChanged && !firstFrame && applied.geometryKey === geometryKey;
    const focusChanged = applied.focusId !== scene.focusId;
    const activeChanged = applied.activeId !== scene.activeId;

    if (stopsChanged) state.markers = syncMarkers(state.markers, state.surface, scene, events);
    if (stopsChanged || activeChanged) markActive(state.markers, scene.activeId);
    if (routesChanged) setRoutes(state.surface.map, scene.routes);

    let framed = false;
    if (frameChanged) {
      moveCamera(state.surface.map, scene, durationFor(scene, firstFrame || paddingOnly));
      framed = true;
    } else if (applied.pitch !== scene.pitch) {
      // Omit padding. MapLibre stores easeTo padding and then adds it again on fitBounds.
      state.surface.map.easeTo({
        pitch: scene.pitch,
        duration: durationFor(scene, false),
        essential: true,
      });
    }
    if (!framed && focusChanged && scene.focusId) {
      const stop = scene.stops.find((item) => item.id === scene.focusId);
      if (stop && offscreen(state.surface.map, stop.at, scene.padding, host)) {
        state.surface.map.easeTo({
          center: stop.at,
          duration: durationFor(scene, false),
          essential: true,
        });
      }
    }
    state.applied = {
      stopsKey: scene.stopsKey,
      routesKey: scene.routesKey,
      frameKey: scene.frameKey,
      geometryKey,
      pitch: scene.pitch,
      focusId: scene.focusId,
      activeId: scene.activeId,
    };
  }

  function refit() {
    if (state.phase !== "ready") return;
    moveCamera(state.surface.map, state.latest, durationFor(state.latest, false));
  }

  function zoomBy(step: 1 | -1) {
    if (state.phase !== "ready") return;
    const duration = state.latest.motion === "instant" ? 0 : 200;
    if (step === 1) state.surface.map.zoomIn({ duration });
    else state.surface.map.zoomOut({ duration });
  }

  function destroy() {
    if (state.phase === "dead") return;
    state.observer.disconnect();
    if (state.phase === "opening") {
      state.abort.abort();
      state.surface?.map.remove();
    }
    if (state.phase === "ready") {
      for (const entry of state.markers.values()) entry.handle.remove();
      state.surface.map.remove();
    }
    state = { phase: "dead" };
  }

  if (!hasWebGL()) {
    queueMicrotask(() => events.failed("no-webgl"));
    return { apply() {}, refit() {}, zoomBy() {}, destroy() {} };
  }

  // ChoiceLayout mounts the map inside display:none. Wait for a real size so a hidden map is not a billed load.
  state = { phase: "sizing", latest: first, observer };
  observer.observe(host);
  onResize();

  return { apply, refit, zoomBy, destroy };
}

function durationFor(scene: TripScene, instant: boolean): number {
  if (instant || scene.motion === "instant") return 0;
  return ANIMATED_MS;
}

function startCamera(scene: TripScene): { center: LngLat; zoom: number; pitch: 0 | 48 } {
  const frame = scene.frame;
  if (frame.kind === "point") return { center: frame.at, zoom: 13, pitch: scene.pitch };
  if (frame.kind === "world") return { center: [0, 20], zoom: 1.5, pitch: 0 };
  const [sw, ne] = frame.bounds;
  return {
    center: [(sw[0] + ne[0]) / 2, (sw[1] + ne[1]) / 2],
    zoom: frame.scale === "region" ? 3 : 12,
    pitch: frame.scale === "region" ? 0 : scene.pitch,
  };
}

function moveCamera(map: GlSurface["map"], scene: TripScene, duration: number) {
  // MapLibre fitBounds adds the map's stored padding to the options padding. Clear first.
  map.setPadding({ top: 0, right: 0, bottom: 0, left: 0 });
  const move = { padding: scene.padding, duration, essential: true as const };
  const frame = scene.frame;
  if (frame.kind === "fit") {
    map.fitBounds(frame.bounds, {
      ...move,
      pitch: frame.scale === "region" ? 0 : scene.pitch,
      maxZoom: frame.scale === "region" ? 6 : 14,
    });
    return;
  }
  if (frame.kind === "point") {
    const [lng, lat] = frame.at;
    const pad = 0.002;
    map.fitBounds(
      [
        [lng - pad, lat - pad],
        [lng + pad, lat + pad],
      ],
      { ...move, pitch: scene.pitch, maxZoom: 13 },
    );
    return;
  }
  map.fitBounds(
    [
      [-20, -20],
      [20, 40],
    ],
    { ...move, pitch: 0, maxZoom: 1.5 },
  );
}

function syncMarkers(
  current: Map<string, MarkerEntry>,
  surface: GlSurface,
  scene: TripScene,
  events: ControllerEvents,
): Map<string, MarkerEntry> {
  const next = new Map<string, MarkerEntry>();
  for (const stop of scene.stops) {
    const existing = current.get(stop.id);
    if (!existing) {
      const element = markerElement(stop);
      element.addEventListener("click", () => events.stopPressed(stop.id));
      next.set(stop.id, { element, handle: surface.marker(element, stop.at), drawn: stop });
      continue;
    }
    current.delete(stop.id);
    if (existing.drawn.label !== stop.label || existing.drawn.glyph !== stop.glyph || existing.drawn.tone !== stop.tone) {
      paintMarker(existing.element, stop);
    }
    if (existing.drawn.at[0] !== stop.at[0] || existing.drawn.at[1] !== stop.at[1]) existing.handle.setLngLat(stop.at);
    existing.drawn = stop;
    next.set(stop.id, existing);
  }
  for (const stale of current.values()) stale.handle.remove();
  return next;
}

function markerElement(stop: SceneStop): HTMLButtonElement {
  const button = document.createElement("button");
  const badge = document.createElement("span");
  const text = document.createElement("span");
  button.type = "button";
  button.className = "swan-marker";
  badge.className = "swan-marker-badge";
  text.className = "swan-marker-label";
  button.append(badge, text);
  paintMarker(button, stop);
  return button;
}

function paintMarker(button: HTMLButtonElement, stop: SceneStop) {
  button.dataset.tone = stop.tone;
  button.setAttribute("aria-label", stop.label);
  const badge = button.querySelector(".swan-marker-badge");
  const text = button.querySelector(".swan-marker-label");
  if (badge) badge.textContent = stop.glyph;
  if (text) text.textContent = stop.label;
}

function markActive(markers: Map<string, MarkerEntry>, activeId: string | null) {
  for (const [id, entry] of markers) {
    const on = id === activeId;
    entry.element.classList.toggle("swan-marker-active", on);
    const parent = entry.element.parentElement;
    if (!parent) continue;
    if (on) parent.style.zIndex = "3";
    else if (parent.style.zIndex === "3") parent.style.removeProperty("z-index");
  }
}

function setRoutes(map: GlSurface["map"], routes: TripScene["routes"]) {
  const source = map.getSource(ROUTE_SOURCE);
  if (!source || typeof source !== "object" || !("setData" in source)) return;
  const setData = source.setData;
  if (typeof setData !== "function") return;
  setData.call(source, routes);
}

function addRoutes(surface: GlSurface, scene: TripScene, ink: string, paper: string) {
  surface.map.addSource(ROUTE_SOURCE, { type: "geojson", data: scene.routes });
  for (const role of Object.keys(ROUTE_STYLE) as RouteRole[]) {
    const style = ROUTE_STYLE[role];
    const filter: RouteLayer["filter"] = ["==", ["get", "role"], role];
    const layout: RouteLayer["layout"] = { "line-cap": "round", "line-join": "round" };
    surface.addRouteLayer({
      id: `swan-route-${role}-casing`,
      type: "line",
      source: ROUTE_SOURCE,
      filter,
      layout,
      paint: { "line-color": paper, "line-width": style.casing, "line-opacity": 0.95 },
    });
    surface.addRouteLayer({
      id: `swan-route-${role}`,
      type: "line",
      source: ROUTE_SOURCE,
      filter,
      layout,
      paint: {
        "line-color": ink,
        "line-width": style.width,
        ...(style.dash ? { "line-dasharray": style.dash } : {}),
      },
    });
  }
}

function offscreen(map: GlSurface["map"], at: LngLat, padding: Insets, host: HTMLElement): boolean {
  const point = map.project(at);
  return point.x < padding.left || point.y < padding.top || point.x > host.clientWidth - padding.right || point.y > host.clientHeight - padding.bottom;
}

function frameGeometryKey(frame: Frame): string {
  if (frame.kind === "world") return "world";
  if (frame.kind === "point") return `point:${frame.at[0].toFixed(5)},${frame.at[1].toFixed(5)}`;
  const [sw, ne] = frame.bounds;
  return `fit:${frame.scale}:${sw.map((value) => value.toFixed(5)).join(",")}:${ne.map((value) => value.toFixed(5)).join(",")}`;
}

function readInk(host: HTMLElement): { ink: string; paper: string } {
  const style = getComputedStyle(host);
  return {
    ink: style.getPropertyValue("--swan-fg").trim() || "#111111",
    paper: style.getPropertyValue("--swan-bg").trim() || "#ffffff",
  };
}

function readError(event: unknown): { sourceId?: string; tile?: unknown; message?: string } {
  if (!event || typeof event !== "object") return {};
  const record = event as { sourceId?: string; tile?: unknown; error?: { message?: string } };
  return { sourceId: record.sourceId, tile: record.tile, message: record.error?.message };
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
