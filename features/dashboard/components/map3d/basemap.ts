import type { Insets, LngLat, Routes } from "./scene";

/** A Mapbox public token. Only parseMapboxToken creates one. */
export type MapboxToken = string & { readonly __brand: "MapboxPublicToken" };

let warnedSecret = false;

/** "" or unset returns null. "pk.…" returns a token. Anything else falls back to the free basemap. */
export function parseMapboxToken(raw: string | undefined): MapboxToken | null {
  const value = raw?.trim() ?? "";
  if (!value) return null;
  if (value.startsWith("pk.")) return value as MapboxToken;
  if (!warnedSecret) {
    warnedSecret = true;
    console.error("NEXT_PUBLIC_MAPBOX_TOKEN must be a public pk. token. Using the free basemap.");
  }
  return null;
}

export interface StartCamera {
  center: LngLat;
  zoom: number;
  pitch: 0 | 48;
}

type CameraMove = { padding: Insets; pitch?: number; duration: number; essential: true };

/** The slice of a GL map the controller drives. Both engines satisfy it through the wrappers below. */
export interface GlMap {
  on(type: "style.load" | "error" | "webglcontextlost", listener: (event: unknown) => void): void;
  addSource(id: string, source: { type: "geojson"; data: Routes }): void;
  getSource(id: string): unknown;
  fitBounds(bounds: [LngLat, LngLat], options: CameraMove & { maxZoom: number }): void;
  easeTo(options: CameraMove & { center?: LngLat; zoom?: number }): void;
  zoomIn(options: { duration: number }): void;
  zoomOut(options: { duration: number }): void;
  project(at: LngLat): { x: number; y: number };
  resize(): void;
  remove(): void;
  isStyleLoaded(): boolean;
}

export interface GlMarker {
  setLngLat(at: LngLat): unknown;
  remove(): void;
}

export interface RouteLayer {
  id: string;
  type: "line";
  source: string;
  filter: ["==", ["get", "role"], string];
  layout: { "line-cap": "round"; "line-join": "round" };
  paint: {
    "line-color": string;
    "line-width": number;
    "line-opacity"?: number;
    "line-dasharray"?: [number, number];
  };
}

export interface GlSurface {
  map: GlMap;
  /** Badge center sits on the coordinate. The element hangs to the right of a left anchor. */
  marker(element: HTMLElement, at: LngLat): GlMarker;
  /** Route ink above roads and below labels. */
  addRouteLayer(layer: RouteLayer): void;
}

export interface Basemap {
  name: "mapbox-standard" | "openfreemap-positron";
  /**
   * Imports one engine and constructs one map.
   * Resolves null when `signal` already aborted, without constructing a map.
   */
  open(container: HTMLElement, start: StartCamera, signal: AbortSignal): Promise<GlSurface | null>;
}

function pickBasemap(token: MapboxToken | null): Basemap {
  return token ? mapboxStandard(token) : openFreeMapPositron;
}

/** The one place that defines the Mapbox Standard look. */
const STANDARD_CONFIG: { [key: string]: unknown } = {
  lightPreset: "day",
  theme: "faded",
  font: "Inter",
  showPointOfInterestLabels: false,
  showTransitLabels: true,
  show3dObjects: true,
};

const POSITRON = "https://tiles.openfreemap.org/styles/positron";

function mapboxStandard(token: MapboxToken): Basemap {
  return {
    name: "mapbox-standard",
    async open(container, start, signal) {
      const mapboxgl = await import("mapbox-gl");
      await import("mapbox-gl/dist/mapbox-gl.css");
      if (signal.aborted) return null;
      const map = new mapboxgl.Map({
        container,
        accessToken: token,
        style: "mapbox://styles/mapbox/standard",
        config: { basemap: STANDARD_CONFIG },
        projection: "mercator",
        language: "en",
        logoPosition: "bottom-left",
        attributionControl: true,
        center: start.center,
        zoom: start.zoom,
        pitch: start.pitch,
      });
      if (signal.aborted) {
        map.remove();
        return null;
      }
      return {
        map: {
          on(type, listener) {
            if (type === "style.load") map.on("style.load", () => listener(undefined));
            else if (type === "error") map.on("error", (event) => listener(event));
            else map.on("webglcontextlost", () => listener(undefined));
          },
          addSource: (id, source) => map.addSource(id, source),
          getSource: (id) => map.getSource(id),
          fitBounds: (bounds, options) => map.fitBounds(bounds, options),
          easeTo: (options) => map.easeTo(options),
          zoomIn: (options) => map.zoomIn(options),
          zoomOut: (options) => map.zoomOut(options),
          project: (at) => map.project(at),
          resize: () => map.resize(),
          remove: () => map.remove(),
          isStyleLoaded: () => map.isStyleLoaded(),
        },
        marker: (element, at) => new mapboxgl.Marker({ element, anchor: "left", offset: [-14, 0] }).setLngLat(at).addTo(map),
        addRouteLayer: (layer) => map.addLayer({ ...layer, slot: "middle" }),
      };
    },
  };
}

const openFreeMapPositron: Basemap = {
  name: "openfreemap-positron",
  async open(container, start, signal) {
    const maplibre = await import("maplibre-gl");
    await import("maplibre-gl/dist/maplibre-gl.css");
    if (signal.aborted) return null;
    const map = new maplibre.Map({
      container,
      style: POSITRON,
      center: start.center,
      zoom: start.zoom,
      pitch: start.pitch,
      attributionControl: { compact: true },
      maplibreLogo: true,
      logoPosition: "bottom-left",
    });
    if (signal.aborted) {
      map.remove();
      return null;
    }
    let buildings = false;
    const addBuildings = () => {
      if (buildings) return;
      const style = map.getStyle();
      if (!style?.sources || !style.layers) return;
      const source = Object.entries(style.sources).find(([, value]) => value.type === "vector")?.[0];
      if (!source) return;
      buildings = true;
      const before = style.layers.find((layer) => layer.type === "symbol")?.id;
      // Positron is an OpenMapTiles style. Those are the only height fields it publishes.
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
        before,
      );
    };
    map.on("style.load", addBuildings);
    return {
      map: {
        on(type, listener) {
          if (type === "style.load") map.on("style.load", () => listener(undefined));
          else if (type === "error") map.on("error", (event) => listener(event));
          else map.on("webglcontextlost", () => listener(undefined));
        },
        addSource: (id, source) => map.addSource(id, source),
        getSource: (id) => map.getSource(id),
        fitBounds: (bounds, options) => map.fitBounds(bounds, options),
        easeTo: (options) => map.easeTo(options),
        zoomIn: (options) => map.zoomIn(options),
        zoomOut: (options) => map.zoomOut(options),
        project: (at) => map.project(at),
        resize: () => map.resize(),
        remove: () => map.remove(),
        isStyleLoaded: () => Boolean(map.isStyleLoaded()),
      },
      marker: (element, at) => new maplibre.Marker({ element, anchor: "left", offset: [-14, 0] }).setLngLat(at).addTo(map),
      addRouteLayer(layer) {
        const style = map.getStyle();
        const before = style?.layers?.find((item) => item.type === "symbol")?.id;
        map.addLayer(layer, before);
      },
    };
  },
};

/** Resolved once. NEXT_PUBLIC_ variables are inlined at build time. */
export const basemap: Basemap = pickBasemap(parseMapboxToken(process.env.NEXT_PUBLIC_MAPBOX_TOKEN));
