import type {
  AttractionSelection,
  CheckoutResult,
  InspectorEvent,
  PackageChoices,
  PlanRevision,
  PlanSelection,
  PlanView,
  PolicyConfig,
  Proposal,
  ScenarioName,
  Suggestion,
  SuggestionAction,
  SuggestionResult,
  SwanView,
  TravelPackage,
  TravelSegment,
  TripBrief,
  TripRequest,
  TripView,
  UserProfile,
  WalletState,
} from "@contracts/api";
import { mockClient } from "./mock";
import type { Constraints } from "./proposalOps";
import { realClient } from "./real";

export interface RoamClient {
  mode: "mock" | "real";
  getPolicy(): Promise<PolicyConfig>;
  putPolicy(policy: PolicyConfig): Promise<PolicyConfig>;
  /** Agent replies and quotes arrive as events; the response is informational. */
  chat(message: string): Promise<void>;
  checkout(invoiceIds: string[]): Promise<CheckoutResult>;
  runScenario(name: ScenarioName): Promise<void>;
  getWallet(): Promise<WalletState>;
  subscribe(onEvent: (e: InspectorEvent) => void, onStatus?: (status: "live" | "down") => void): () => void;
  createPlan(brief: TripBrief): Promise<{ plan_id: string }>;
  getPlan(id: string): Promise<PlanView>;
  submitSelection(id: string, selection: PlanSelection): Promise<{ ok: boolean }>;
  revisePlan(id: string, revision: PlanRevision): Promise<{ ok: boolean }>;
  lookupFlight(number: string, date: string): Promise<TravelSegment>;
  demoSignIn(): Promise<{ token: string; user_id: string }>;
  magicLink(email: string): Promise<{ token: string; user_id: string }>;
  getProfile(): Promise<UserProfile | null>;
  putProfile(profile: UserProfile): Promise<UserProfile>;
  deleteAccount(): Promise<void>;
  requestTrip(request: TripRequest): Promise<{ plan_id: string; phase: string }>;
  getSwan(id: string): Promise<SwanView>;
  submitAttractions(id: string, selection: AttractionSelection): Promise<{ ok: boolean; phase: string }>;
  choosePackage(id: string, choices: PackageChoices): Promise<{ ok: boolean; phase: string }>;
  getPackage(id: string): Promise<TravelPackage>;
  createTrip(message: string): Promise<{ trip_id: string }>;
  getTrip(id: string): Promise<TripView>;
  suggestionAlternatives(id: string, sid: string, constraints?: Constraints): Promise<Suggestion[]>;
  actOnSuggestion(id: string, action: SuggestionAction): Promise<SuggestionResult>;
  acceptAll(id: string): Promise<Proposal>;
}

export function getClient(): RoamClient {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "0" ? realClient : mockClient;
}
