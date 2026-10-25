import { readFileSync } from "node:fs";
import { apply, initialState } from "../lib/proposalOps.ts";

const fixtures = new URL("../../../contracts/fixtures/", import.meta.url);
const read = (name) => JSON.parse(readFileSync(new URL(name, fixtures), "utf8"));
const script = read("conversation_kyoto.json");
const catalog = {
  flights: read("flight_offers.json"),
  hotels: read("hotel_offers.json"),
  candidates: read("candidates_kyoto.json").candidates,
};

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function comparable(proposal) {
  const totals = Object.fromEntries(Object.entries(proposal.totals).map(([key, value]) => [key, key === "currency" ? value : Number(value)]));
  return JSON.stringify(canonical({ ...proposal, totals }));
}

function firstDifference(left, right, path = "") {
  if (JSON.stringify(left) === JSON.stringify(right)) return null;
  if (left && right && typeof left === "object" && typeof right === "object") {
    for (const key of new Set([...Object.keys(left), ...Object.keys(right)])) {
      const found = firstDifference(left[key], right[key], `${path}.${key}`);
      if (found) return found;
    }
  }
  return `${path}: got ${JSON.stringify(left)?.slice(0, 160)} want ${JSON.stringify(right)?.slice(0, 160)}`;
}

let failed = 0;
for (const name of ["accept", "modify", "reject"]) {
  const scripted = script[name];
  const got = apply(initialState(script.proposal), scripted.action, catalog).proposal;
  const same = comparable(got) === comparable(scripted.proposal);
  if (!same) failed += 1;
  const detail = same ? "" : ` ${firstDifference(JSON.parse(comparable(got)), JSON.parse(comparable(scripted.proposal)))}`;
  console.log(`${same ? "PASS" : "FAIL"} ${name} ${scripted.action.suggestion_id}${detail}`);
}
console.log(failed ? `result: FAIL (${failed})` : "result: PASS");
process.exit(failed ? 1 : 0);
