/**
 * Exhaustive sequential check of the mock checkout leash.
 *
 * The harness transpiles features/dashboard/lib/mock.ts and calls its real
 * evaluate and checkout. Imports are replaced because this process has no
 * Next.js path aliases. The demo pause is resolved immediately so a sequential
 * run keeps the same step order without the 850ms UI delay. That pause is not
 * part of the decision.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../..");
const mockPath = join(repoRoot, "features/dashboard/lib/mock.ts");
const policyPath = join(repoRoot, "contracts/fixtures/policy.json");
const quotesPath = join(repoRoot, "contracts/fixtures/quotes.json");

const SOURCE_SHA = createHash("sha256").update(readFileSync(mockPath)).digest("hex");

function cents(value) {
  const raw = String(value);
  if (!/^-?\d+(\.\d{1,2})?$/.test(raw)) {
    throw new Error(`money is not a cent string: ${raw}`);
  }
  const neg = raw.startsWith("-");
  const [whole, frac = ""] = raw.replace("-", "").split(".");
  const n = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  return neg ? -n : n;
}

function mustReplace(source, needle, replacement, label) {
  if (!source.includes(needle)) {
    throw new Error(`harness no longer matches mock.ts (${label})`);
  }
  return source.replace(needle, replacement);
}

function ensureTypescript() {
  const installed = join(here, "node_modules", "typescript", "package.json");
  if (existsSync(installed)) return;
  const result = spawnSync("npm", ["install", "--silent"], {
    cwd: here,
    stdio: "inherit",
    shell: true,
  });
  if (result.status !== 0) {
    throw new Error("npm install of typescript failed");
  }
}

function buildHarness(ts, source) {
  let body = source.replace(/^\s*import\s[\s\S]*?;\s*$/gm, "");
  body = mustReplace(
    body,
    "const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));",
    "const sleep = (_ms: number) => Promise.resolve();",
    "demo pause",
  );
  if (!body.includes("function evaluate(") || !body.includes("async function checkout(")) {
    throw new Error("harness no longer matches mock.ts (evaluate or checkout)");
  }
  const policyFx = readFileSync(policyPath, "utf8");
  const quotesFx = readFileSync(quotesPath, "utf8");
  const header = `const policyFx = ${policyFx};\nconst quotesFx = ${quotesFx};\n`;
  const footer = `
export function __reset(policy, spentToday, balance) {
  state.policy = structuredClone(policy);
  state.spentToday = spentToday;
  state.balance = balance;
  state.escrows.clear();
  state.listeners.clear();
  state.seq = 0;
  state.seqTx = 100;
}
export function __evaluate(quotes) {
  return evaluate(quotes);
}
export async function __checkout(quotes) {
  const events = [];
  const listener = (event) => events.push(event.type);
  state.listeners.add(listener);
  const beforeBalance = state.balance;
  const beforeSpent = state.spentToday;
  const beforeEscrow = state.escrows.size;
  try {
    const result = await checkout(quotes);
    return { result, events, beforeBalance, beforeSpent, beforeEscrow, balance: state.balance, spentToday: state.spentToday, escrow: state.escrows.size };
  } finally {
    state.listeners.delete(listener);
  }
}
`;
  const transpiled = ts.transpileModule(header + body + footer, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
    fileName: "mock.ts",
  });
  if (transpiled.diagnostics?.length) {
    const text = ts.formatDiagnostics(transpiled.diagnostics, {
      getCanonicalFileName: (f) => f,
      getCurrentDirectory: () => repoRoot,
      getNewLine: () => "\n",
    });
    throw new Error(text);
  }
  return transpiled.outputText;
}

async function loadHarness() {
  ensureTypescript();
  const ts = await import("typescript");
  const source = readFileSync(mockPath, "utf8");
  const dir = mkdtempSync(join(tmpdir(), "roam-leash-"));
  const file = join(dir, "harness.mjs");
  writeFileSync(file, buildHarness(ts, source));
  return import(pathToFileURL(file).href);
}

function quoteOf({ amount, verified, category, id }) {
  return {
    invoice_id: id,
    merchant_id: "grid",
    merchant_name: "Grid Merchant",
    merchant_address: "rGrid",
    sku: "GRID",
    title: "Grid item",
    category,
    amount,
    currency: "RLUSD",
    viator_price: amount,
    slot_start: "2026-11-14T14:00:00+09:00",
    slot_end: "2026-11-14T15:00:00+09:00",
    location: { lat: 35.01, lng: 135.67 },
    cancel_after: "2026-11-14T13:00:00+09:00",
    expires_at: "2026-11-14T23:00:00+09:00",
    merchant_signature: "00",
    merchant_verified: verified,
  };
}

function violates(quotes, policy, spentStr) {
  const reasons = [];
  let sum = 0;
  const itemCap = cents(policy.max_per_item);
  const remaining = cents(policy.max_daily_budget) - cents(spentStr);
  for (const q of quotes) {
    const amount = cents(q.amount);
    sum += amount;
    if (amount > itemCap) {
      reasons.push(`max_per_item on ${q.invoice_id}: ${q.amount} > ${policy.max_per_item}`);
    }
    if (policy.require_verified_credential && q.merchant_verified !== true) {
      reasons.push(`verified_credential on ${q.invoice_id}: merchant_verified is ${q.merchant_verified}`);
    }
    if (!policy.allowed_categories.includes(q.category)) {
      reasons.push(`category on ${q.invoice_id}: ${q.category}`);
    }
  }
  if (sum > remaining) {
    reasons.push(`max_daily_budget: sum ${sum} cents > remaining ${remaining} cents`);
  }
  return reasons;
}

function problemsOf(reasons, decision, out) {
  if (reasons.length === 0) return [];
  const problems = [];
  if (decision.approved !== false) problems.push("evaluate set approved true");
  if (out.result.status !== "blocked") problems.push(`checkout status is ${out.result.status}`);
  if (out.result.decision?.approved !== false) problems.push("checkout decision is approved");
  const leaked = out.events.filter((type) => type === "batch.submitted" || type === "batch.validated");
  if (leaked.length) problems.push(`emitted ${leaked.join(" and ")}`);
  if (out.balance !== out.beforeBalance) problems.push(`balance moved from ${out.beforeBalance} to ${out.balance}`);
  if (out.spentToday !== out.beforeSpent) problems.push(`spent_today moved from ${out.beforeSpent} to ${out.spentToday}`);
  if (out.escrow !== out.beforeEscrow) problems.push("an escrow was recorded");
  return problems;
}

function numericLemma() {
  const limit = 20001;
  const num = new Float64Array(limit);
  for (let c = 0; c < limit; c++) {
    const whole = Math.floor(c / 100);
    const frac = String(c % 100).padStart(2, "0");
    num[c] = Number(`${whole}.${frac}`);
  }
  for (let c = 1; c < limit; c++) {
    if (!(num[c] > num[c - 1])) {
      return `Number comparison is not monotonic at ${c} cents`;
    }
  }
  const quoteLimit = 10001;
  for (let a = 0; a <= quoteLimit; a++) {
    for (let b = a; b <= quoteLimit; b++) {
      const sum = a + b;
      if (sum >= limit) continue;
      if (num[a] + num[b] <= num[sum - 1]) {
        return `float sum of ${a} and ${b} cents does not sit strictly above the previous cent`;
      }
    }
  }
  for (let spent = 0; spent <= 10000; spent++) {
    for (let budget = spent; budget <= 10000; budget++) {
      const over = budget - spent + 1;
      if (over >= limit) continue;
      const remaining = num[budget] - num[spent];
      if (!(num[over] > remaining)) {
        return `amount ${over} cents is not above remaining budget ${budget}-${spent}`;
      }
    }
  }
  return null;
}

function policies() {
  const demo = JSON.parse(readFileSync(policyPath, "utf8"));
  return [
    { name: "demo-default", ...demo },
    {
      name: "tight",
      max_daily_budget: "50.00",
      max_per_item: "20.00",
      currency: "RLUSD",
      require_verified_credential: true,
      allowed_categories: ["activity", "food"],
      date_window_start: null,
      date_window_end: null,
      geofence: null,
    },
    {
      name: "souvenir-allowed",
      max_daily_budget: "600.00",
      max_per_item: "500.00",
      currency: "RLUSD",
      require_verified_credential: false,
      allowed_categories: ["activity", "food", "shopping", "transport", "lodging"],
      date_window_start: null,
      date_window_end: null,
      geofence: null,
    },
  ];
}

function cases() {
  const fixtures = JSON.parse(readFileSync(quotesPath, "utf8"));
  const bySku = Object.fromEntries(fixtures.map((q) => [q.sku, q]));
  const list = [];
  list.push({
    label: "fixture trap under demo policy",
    policyName: "demo-default",
    spent: "0.00",
    quotes: [bySku["GOLD-CAT"]],
  });
  list.push({
    label: "fixture bike and matcha under demo policy",
    policyName: "demo-default",
    spent: "0.00",
    quotes: [bySku["BIKE-2H"], bySku["MATCHA-WS"]],
  });
  list.push({
    label: "fixture matcha under the tight cap",
    policyName: "tight",
    spent: "0.00",
    quotes: [bySku["MATCHA-WS"]],
  });

  const amounts = ["0.00", "15.00", "20.00", "30.00", "45.00", "45.01", "60.00", "70.00", "500.00"];
  const verifieds = [true, false, null];
  const categories = ["activity", "food", "shopping"];
  const spentValues = ["0.00", "55.00", "80.00", "100.00"];
  let n = 0;
  for (const amount of amounts) {
    for (const verified of verifieds) {
      for (const category of categories) {
        n += 1;
        list.push({
          label: `grid one ${amount} ${category} verified=${verified}`,
          policyName: "*",
          spent: "*",
          quotes: [quoteOf({ amount, verified, category, id: `ONE-${n}` })],
        });
      }
    }
  }
  const pairAmounts = ["15.00", "30.00", "45.01", "60.00"];
  const pairVerified = [true, false];
  const pairCategory = ["food", "shopping"];
  const pairChoices = [];
  for (const amount of pairAmounts) {
    for (const verified of pairVerified) {
      for (const category of pairCategory) {
        pairChoices.push({ amount, verified, category });
      }
    }
  }
  for (let i = 0; i < pairChoices.length; i++) {
    for (let j = i; j < pairChoices.length; j++) {
      const left = pairChoices[i];
      const right = pairChoices[j];
      list.push({
        label: `grid two ${left.amount}/${right.amount}`,
        policyName: "*",
        spent: "*",
        quotes: [
          quoteOf({ ...left, id: `L-${i}` }),
          quoteOf({ ...right, id: `R-${j}` }),
        ],
      });
    }
  }
  return { list, spentValues };
}

function printFailure(spec, reasons, problems, out) {
  console.log("result: FAIL");
  console.log(`case: ${spec.label}`);
  console.log(`policy: ${spec.policy.name} max_per_item=${spec.policy.max_per_item} max_daily_budget=${spec.policy.max_daily_budget} require_verified_credential=${spec.policy.require_verified_credential} spent_today=${spec.spent}`);
  console.log("quotes:");
  for (const q of spec.quotes) {
    console.log(`  ${q.sku} ${q.invoice_id} amount=${q.amount} category=${q.category} merchant_verified=${q.merchant_verified}`);
  }
  console.log("oracle:");
  for (const reason of reasons) console.log(`  ${reason}`);
  console.log("checkout steps that broke the leash:");
  console.log("  evaluate ran on those quotes");
  console.log(`  events: ${out.events.join(", ") || "(none)"}`);
  for (const problem of problems) console.log(`  ${problem}`);
}

async function main() {
  console.log(`covered: features/dashboard/lib/mock.ts evaluate, checkout`);
  console.log(`source_sha256: ${SOURCE_SHA}`);
  const lemma = numericLemma();
  if (lemma) {
    console.log("result: FAIL");
    console.log(`numeric bound: ${lemma}`);
    process.exitCode = 1;
    return;
  }
  console.log("numeric bound: Number comparisons of cent strings from 0.00 through 200.00 match integer cents for one value, a two-value sum, and budget minus spent");
  const harness = await loadHarness();
  const policyList = policies();
  const byName = Object.fromEntries(policyList.map((p) => [p.name, p]));
  const { list, spentValues } = cases();
  let checked = 0;
  let violating = 0;
  for (const item of list) {
    const usePolicies = item.policyName === "*" ? policyList : [byName[item.policyName]];
    const useSpent = item.spent === "*" ? spentValues : [item.spent];
    for (const policy of usePolicies) {
      for (const spent of useSpent) {
        const reasons = violates(item.quotes, policy, spent);
        harness.__reset(policy, Number(spent), 250);
        const decision = harness.__evaluate(item.quotes);
        const out = await harness.__checkout(item.quotes);
        checked += 1;
        if (reasons.length) violating += 1;
        const problems = problemsOf(reasons, decision, out);
        if (problems.length) {
          printFailure({ ...item, policy, spent }, reasons, problems, out);
          console.log(`checked_before_fail: ${checked}`);
          process.exitCode = 1;
          return;
        }
      }
    }
  }
  console.log(`cases: ${checked}`);
  console.log(`violating: ${violating}`);
  console.log("result: PASS");
}

main().catch((error) => {
  console.log("result: HARNESS");
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 2;
});
