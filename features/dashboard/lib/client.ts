import type {
  CheckoutResult,
  InspectorEvent,
  PolicyConfig,
  ScenarioName,
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
  /** Mock resolves when the scenario finishes; real resolves once the gateway accepts it. */
  runScenario(name: ScenarioName): Promise<void>;
  getWallet(): Promise<WalletState>;
  subscribe(onEvent: (e: InspectorEvent) => void): () => void;
}

export function getClient(): RoamClient {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "0" ? realClient : mockClient;
}
