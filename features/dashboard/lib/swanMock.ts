import type {
  AttractionSelection,
  FlightOffer,
  HotelOffer,
  PackageChoices,
  SwanView,
  TravelPackage,
  TripRequest,
  UserProfile,
} from "@contracts/api";
import flightsFx from "@fixtures/flight_offers.json";
import hotelsFx from "@fixtures/hotel_offers.json";
import packageFx from "@fixtures/package_kyoto.json";
import profileFx from "@fixtures/profile.json";

const PROFILE_KEY = "swan.profile";
const TOKEN_KEY = "swan.token";
const TRIPS_KEY = "swan.trips";

type StoredTrip = {
  request: TripRequest;
  phase: SwanView["phase"];
  flights: FlightOffer[];
  hotels: HotelOffer[];
  package: TravelPackage | null;
  selection: AttractionSelection | null;
};

function readTrips(): Record<string, StoredTrip> {
  if (typeof window === "undefined") return {};
  const raw = sessionStorage.getItem(TRIPS_KEY);
  return raw ? JSON.parse(raw) as Record<string, StoredTrip> : {};
}

function writeTrips(trips: Record<string, StoredTrip>) {
  sessionStorage.setItem(TRIPS_KEY, JSON.stringify(trips));
}

function view(id: string, trip: StoredTrip): SwanView {
  return {
    plan_id: id,
    phase: trip.phase,
    request: trip.request,
    flights: trip.flights,
    hotels: trip.hotels,
    package: trip.package,
  };
}

function advance(trip: StoredTrip) {
  const auto = trip.request.autonomy;
  if (auto.attractions === "i_choose" && !trip.selection) {
    trip.phase = "waiting_attractions";
    trip.package = null;
    return;
  }
  trip.flights = flightsFx as FlightOffer[];
  if (auto.flights === "i_choose" && !trip.package) {
    trip.phase = "waiting_flights";
    return;
  }
  trip.hotels = hotelsFx as HotelOffer[];
  if (auto.hotels === "i_choose" && !trip.package) {
    trip.phase = "waiting_hotels";
    return;
  }
  trip.package = structuredClone(packageFx) as TravelPackage;
  trip.phase = "ready";
}

export const swanMock = {
  async demoSignIn() {
    const profile = profileFx as UserProfile;
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    localStorage.setItem(TOKEN_KEY, "demo");
    return { token: "demo", user_id: profile.user_id };
  },
  async magicLink(email: string) {
    localStorage.setItem(TOKEN_KEY, email);
    return { token: email, user_id: email };
  },
  async getProfile() {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? JSON.parse(raw) as UserProfile : null;
  },
  async putProfile(profile: UserProfile) {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    return profile;
  },
  async deleteAccount() {
    localStorage.removeItem(PROFILE_KEY);
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TRIPS_KEY);
  },
  async requestTrip(request: TripRequest) {
    const id = `swan-${crypto.randomUUID().slice(0, 8)}`;
    const trip: StoredTrip = {
      request,
      phase: "waiting_attractions",
      flights: [],
      hotels: [],
      package: null,
      selection: null,
    };
    advance(trip);
    const trips = readTrips();
    trips[id] = trip;
    writeTrips(trips);
    return { plan_id: id, phase: trip.phase };
  },
  async getSwan(id: string) {
    const trip = readTrips()[id];
    if (!trip) throw new Error("This trip is not on this browser yet.");
    return view(id, trip);
  },
  async submitAttractions(id: string, selection: AttractionSelection) {
    const trips = readTrips();
    const trip = trips[id];
    if (!trip) throw new Error("This trip is not on this browser yet.");
    trip.selection = selection;
    trip.request = {
      ...trip.request,
      autonomy: { ...trip.request.autonomy, attractions: selection.mode },
    };
    trip.package = null;
    advance(trip);
    writeTrips(trips);
    return { ok: true, phase: trip.phase };
  },
  async choosePackage(id: string, choices: PackageChoices) {
    const trips = readTrips();
    const trip = trips[id];
    if (!trip) throw new Error("This trip is not on this browser yet.");
    const handed = !choices.outbound_id && !choices.return_id && !choices.hotel_ids?.length;
    if (handed) {
      if (trip.phase === "waiting_flights") trip.request.autonomy.flights = "swan_decides";
      if (trip.phase === "waiting_hotels") trip.request.autonomy.hotels = "swan_decides";
      trip.package = null;
      advance(trip);
      writeTrips(trips);
      return { ok: true, phase: trip.phase };
    }
    const base = (trip.package ?? structuredClone(packageFx)) as TravelPackage;
    if (choices.outbound_id) {
      base.outbound = trip.flights.find((item) => item.id === choices.outbound_id) ?? base.outbound;
    }
    if (choices.return_id) {
      base.return = trip.flights.find((item) => item.id === choices.return_id) ?? base.return;
    }
    if (choices.hotel_ids?.length) {
      const picked = trip.hotels.filter((item) => choices.hotel_ids?.includes(item.id));
      if (picked.length) {
        base.hotels = picked.map((offer) => ({
          offer,
          check_in: offer.check_in || trip.request.start_date,
          check_out: offer.check_out || trip.request.end_date,
        }));
      }
    }
    trip.package = base;
    if (trip.request.autonomy.hotels === "i_choose" && !choices.hotel_ids?.length) {
      trip.hotels = hotelsFx as HotelOffer[];
      trip.phase = "waiting_hotels";
    } else {
      trip.phase = "ready";
    }
    writeTrips(trips);
    return { ok: true, phase: trip.phase };
  },
  async getPackage(id: string) {
    const trip = readTrips()[id];
    if (!trip?.package) throw new Error("Swan is still planning this trip.");
    return trip.package;
  },
};
