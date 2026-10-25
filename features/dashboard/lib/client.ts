import type {
  AttractionSelection,
  CheckoutResult,
  InspectorEvent,
  PackageChoices,
  PlanRevision,
  PlanSelection,
  PlanView,
  PolicyConfig,
  ScenarioName,
  SwanView,
  TravelPackage,
  TravelSegment,
  TripBrief,
  TripRequest,
  UserProfile,
  WalletState,
} from "@contracts/api";
import { mockClient } from "./mock";
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
}

export function getClient(): RoamClient {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "0" ? realClient : mockClient;
}
