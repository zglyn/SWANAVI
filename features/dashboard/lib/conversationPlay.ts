import type { ChatMessage, Control, Proposal, TripConversation, TripFacts } from "@contracts/api";
import fixture from "@fixtures/conversation_kyoto.json";

export function kyotoScript(): TripConversation {
  return (fixture as { conversation: TripConversation }).conversation;
}

export function kyotoProposal(): Proposal {
  return (fixture as { proposal: Proposal }).proposal;
}

export function missingFacts(brief: TripFacts): string[] {
  const missing: string[] = [];
  if (!brief.destination) missing.push("destination");
  if (!brief.start_date || !brief.end_date) missing.push("dates");
  if (!brief.origin?.airport_codes?.length && !brief.origin?.place) missing.push("origin");
  if (brief.travellers == null) missing.push("travellers");
  return missing;
}

export interface PlayState {
  messages: ChatMessage[];
  brief: TripFacts;
  mode: "stream" | "ask" | "offer" | "planning";
  cursor: number;
  shown: string;
  answers: Record<string, string | number>;
  status: string;
}

const CONFIRMED: TripFacts = {
  destination: "Kyoto",
  origin: { from_home: true, place: "San Francisco", airport_codes: ["SFO"] },
  start_date: "2026-11-14",
  end_date: "2026-11-17",
};

export function begin(script: ChatMessage[], opening: string): PlayState {
  const first = { ...script[0], text: opening || script[0].text };
  return {
    messages: [first],
    brief: {},
    mode: "stream",
    cursor: 1,
    shown: "",
    answers: {},
    status: "",
  };
}

export function streamTarget(state: PlayState, script: ChatMessage[]): string {
  return script[state.cursor]?.text ?? "";
}

export function advanceStream(state: PlayState, script: ChatMessage[], reduced: boolean): PlayState {
  const target = streamTarget(state, script);
  const shown = reduced || state.shown.length >= target.length
    ? target
    : target.slice(0, state.shown.length + Math.max(1, Math.ceil(target.length / 40)));
  if (shown !== target) return { ...state, shown };
  const message = { ...script[state.cursor], text: target };
  const next: PlayState = {
    ...state,
    messages: [...state.messages, message],
    shown: "",
    cursor: state.cursor + 1,
    brief: { ...state.brief, ...CONFIRMED },
  };
  if (message.controls.length > 0) return { ...next, mode: "ask" };
  if (missingFacts(next.brief).length === 0) return { ...next, mode: "offer" };
  return { ...next, mode: "stream" };
}

export function answerControl(state: PlayState, control: Control, value: string | number): PlayState {
  return { ...state, answers: { ...state.answers, [control.slot]: value } };
}

export function controlsReady(state: PlayState): boolean {
  const last = state.messages[state.messages.length - 1];
  if (!last || state.mode !== "ask") return false;
  return last.controls.every((control) => state.answers[control.slot] != null);
}

export function commitAnswers(state: PlayState, script: ChatMessage[]): PlayState {
  const travellers = Number(state.answers.travellers ?? 2);
  const budget = Number(state.answers.budget ?? 2000);
  const text = `${travellers} of us, about $${budget.toLocaleString("en-US")}`;
  const user = script.find((message) => message.role === "user" && message.answers) ?? script[2];
  return {
    ...state,
    messages: [...state.messages, { ...user, text, answers: [
      { slot: "travellers", value: travellers },
      { slot: "budget", value: String(budget) },
    ] }],
    brief: { ...state.brief, travellers, budget: String(budget) },
    mode: "stream",
    cursor: script.findIndex((message) => message.role === "assistant" && message.controls.length === 0 && message.id !== script[1]?.id),
    answers: state.answers,
  };
}

export function planNow(state: PlayState, script: ChatMessage[]): PlayState {
  const plan = script.find((message) => message.text === "Plan it now") ?? script[4];
  return {
    ...state,
    messages: [...state.messages, plan],
    mode: "planning",
    status: "Finding flights from SFO…",
    brief: { ...state.brief, pace: state.brief.pace ?? "balanced" },
  };
}

export function editFact(brief: TripFacts, id: string, value: string): TripFacts {
  const text = value.trim();
  if (!text) return brief;
  if (id === "destination") return { ...brief, destination: text };
  if (id === "origin") return { ...brief, origin: { from_home: false, place: text, airport_codes: [text.toUpperCase()] } };
  if (id === "travellers") {
    const count = Number(text.replace(/[^0-9]/g, ""));
    return count >= 1 ? { ...brief, travellers: count } : brief;
  }
  if (id === "budget") return { ...brief, budget: text.replace(/[^0-9.]/g, "") || brief.budget };
  if (id === "pace" && (text === "relaxed" || text === "balanced" || text === "packed")) return { ...brief, pace: text };
  return brief;
}

export function factChips(brief: TripFacts): { id: string; label: string; known: boolean }[] {
  const dates = brief.start_date && brief.end_date ? "Nov 14-17" : "";
  const origin = brief.origin?.airport_codes?.[0] ?? "";
  return [
    { id: "destination", label: brief.destination || "Destination", known: Boolean(brief.destination) },
    { id: "dates", label: dates || "Dates", known: Boolean(dates) },
    { id: "origin", label: origin ? `From ${origin}` : "From", known: Boolean(origin) },
    { id: "travellers", label: brief.travellers ? `${brief.travellers} travellers` : "Travellers", known: brief.travellers != null },
    { id: "budget", label: brief.budget ? `$${Number(brief.budget).toLocaleString("en-US")}` : "Budget", known: brief.budget != null },
    { id: "pace", label: brief.pace || "Pace", known: Boolean(brief.pace) },
  ];
}
