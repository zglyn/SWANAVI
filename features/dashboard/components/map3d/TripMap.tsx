"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createTripMapController, type MapFailure, type TripMapController } from "./controller";
import { chromeInsets, deriveScene, type Dimension, type Insets, type MapStop, type SceneStop, type TripScene } from "./scene";

export type { MapStop };

interface Arc {
  from: [number, number];
  to: [number, number];
}

const FAILURE_COPY: Record<MapFailure, string> = {
  "no-webgl": "This browser can't draw maps.",
  style: "The map didn't load.",
  "context-lost": "The browser dropped the map's graphics.",
  engine: "The map could not start.",
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
  const reducedMotion = usePrefersReducedMotion();
  const [chosen, setChosen] = useState<Dimension | null>(null);
  const dimension = chosen ?? (reducedMotion ? "2d" : "3d");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | MapFailure>("loading");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const scene = deriveScene({
    stops,
    arcs,
    focus,
    route,
    highlight,
    padding,
    selectedId,
    dimension,
    reducedMotion,
  });
  const map = useTripMapController(host, scene, {
    stopPressed(id) {
      setSelectedId(id);
      onSelectRef.current?.(id);
    },
    status: setStatus,
  });

  if (isFailure(status)) {
    return <RouteList dayLabel={dayLabel} failure={status} stops={scene.stops} onPick={(id) => { setSelectedId(id); onSelectRef.current?.(id); }} />;
  }

  return (
    <div className="swan-map swan-light" data-ready={status === "ready" ? "true" : "false"} style={insetVars(chromeInsets(scene.padding))}>
      <div ref={host} className="swan-map-canvas" role="region" aria-label={`Map of ${dayLabel}`} />
      <div className="swan-map-bar">
        <MapCaption dayLabel={dayLabel} selected={scene.selected} onClear={() => setSelectedId(null)} />
        <MapControls showToggle={showToggle} dimension={dimension} onDimension={setChosen} onZoom={map.zoomBy} onFit={map.refit} />
      </div>
    </div>
  );
}

function useTripMapController(
  host: React.RefObject<HTMLDivElement | null>,
  scene: TripScene,
  handlers: { stopPressed(id: string): void; status(next: "ready" | MapFailure): void },
): Pick<TripMapController, "refit" | "zoomBy"> {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const controllerRef = useRef<TripMapController | null>(null);
  const api = useRef<Pick<TripMapController, "refit" | "zoomBy">>({
    refit: () => controllerRef.current?.refit(),
    zoomBy: (step) => controllerRef.current?.zoomBy(step),
  });

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    const controller = createTripMapController(node, sceneRef.current, {
      ready() { handlersRef.current.status("ready"); },
      stopPressed(id) { handlersRef.current.stopPressed(id); },
      failed(failure) { handlersRef.current.status(failure); },
    });
    controllerRef.current = controller;
    controller.apply(sceneRef.current);
    return () => {
      controller.destroy();
      controllerRef.current = null;
    };
  }, [host]);

  useEffect(() => {
    controllerRef.current?.apply(scene);
  });

  return api.current;
}

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

function MapCaption({ dayLabel, selected, onClear }: { dayLabel: string; selected: SceneStop | null; onClear(): void }) {
  return (
    <div className="swan-map-slot" data-slot="top-left">
      <div className="swan-map-float swan-map-caption" aria-live="polite">
        <p className="swan-eyebrow">{dayLabel}</p>
        {selected ? (
          <div className="swan-map-caption-stop">
            <span className="swan-marker-badge" data-tone={selected.tone} aria-hidden="true">{selected.glyph}</span>
            <span className="swan-map-caption-label">{selected.label}</span>
            <button type="button" className="swan-map-clear" aria-label={`Clear ${selected.label}`} onClick={onClear}>✕</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MapControls({
  showToggle,
  dimension,
  onDimension,
  onZoom,
  onFit,
}: {
  showToggle: boolean;
  dimension: Dimension;
  onDimension(next: Dimension): void;
  onZoom(step: 1 | -1): void;
  onFit(): void;
}) {
  return (
    <div className="swan-map-slot" data-slot="top-right">
      {showToggle ? (
        <div className="swan-seg swan-map-float" role="radiogroup" aria-label="Map dimension">
          <button type="button" role="radio" aria-checked={dimension === "2d"} onClick={() => onDimension("2d")}>2D</button>
          <button type="button" role="radio" aria-checked={dimension === "3d"} onClick={() => onDimension("3d")}>3D</button>
        </div>
      ) : null}
      <div className="swan-map-zoom" role="group" aria-label="Zoom">
        <button type="button" className="swan-map-btn swan-map-float" aria-label="Zoom out" onClick={() => onZoom(-1)}>−</button>
        <button type="button" className="swan-map-btn swan-map-float" aria-label="Zoom in" onClick={() => onZoom(1)}>+</button>
      </div>
      <button type="button" className="swan-map-btn swan-map-float" aria-label="Fit the trip" onClick={onFit}>
        <span aria-hidden="true">⤢</span>
      </button>
    </div>
  );
}

function RouteList({
  dayLabel,
  failure,
  stops,
  onPick,
}: {
  dayLabel: string;
  failure: MapFailure;
  stops: readonly SceneStop[];
  onPick(id: string): void;
}) {
  return (
    <div className="swan-surface flex h-full min-h-72 flex-col overflow-auto p-5" role="region" aria-label="Route list">
      <p className="swan-eyebrow">Map view is off</p>
      <p className="mt-1 text-xl font-semibold tracking-tight">{dayLabel}</p>
      <p className="swan-muted mt-1 text-sm">{FAILURE_COPY[failure]} Here is the route as a list.</p>
      <ol className="mt-4 space-y-2">
        {stops.map((stop) => (
          <li key={stop.id} className="flex items-center gap-3">
            <span className="swan-marker-badge" data-tone={stop.tone} aria-hidden="true">{stop.glyph}</span>
            <button type="button" className="text-left" onClick={() => onPick(stop.id)}>{stop.label}</button>
          </li>
        ))}
      </ol>
    </div>
  );
}

function isFailure(status: "loading" | "ready" | MapFailure): status is MapFailure {
  return status !== "loading" && status !== "ready";
}

function insetVars(insets: Insets): React.CSSProperties {
  return {
    "--swan-map-inset-top": `${insets.top}px`,
    "--swan-map-inset-right": `${insets.right}px`,
    "--swan-map-inset-bottom": `${insets.bottom}px`,
    "--swan-map-inset-left": `${insets.left}px`,
  } as React.CSSProperties;
}
