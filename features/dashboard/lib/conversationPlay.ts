import type { ChatMessage, Control, Proposal, TripConversation, TripFacts } from "@contracts/api";
import fixture from "@fixtures/conversation_demo.json";
import { demoCity, namesDemo } from "@/lib/demoScope";

export function demoScript(): TripConversation {
  return (fixture as { conversation: TripConversation }).conversation;
}

export function demoProposal(): Proposal {
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

const CONFIRMED = {
  destination: demoCity.destination,
  origin: { from_home: false, airport_codes: [demoCity.origin.code] },
  start_date: demoCity.dates.start,
  end_date: demoCity.dates.end,
  travellers: demoCity.travellers,
  pace: demoCity.pace,
  interests: [...demoCity.interests],
} as TripFacts;

export function begin(script: ChatMessage[], opening: string): PlayState {
  const text = opening || script[0].text;
  const first = { ...script[0], text };
  return {
    messages: [first],
    brief: namesDemo(text) ? { ...CONFIRMED } : {},
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
    brief: namesDemo(state.messages[0]?.text) ? { ...state.brief, ...CONFIRMED } : state.brief,
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
    status: `Finding flights from ${demoCity.origin.code}…`,
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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function chipDates(start: string, end: string): string {
  const startMonth = Number(start.slice(5, 7));
  const endMonth = Number(end.slice(5, 7));
  const startDay = Number(start.slice(8, 10));
  const endDay = Number(end.slice(8, 10));
  if (startMonth === endMonth) return `${MONTHS[startMonth - 1]} ${startDay}-${endDay}`;
  return `${MONTHS[startMonth - 1]} ${startDay}-${MONTHS[endMonth - 1]} ${endDay}`;
}

export function factChips(brief: TripFacts): { id: string; label: string; known: boolean }[] {
  const dates = brief.start_date && brief.end_date ? chipDates(brief.start_date, brief.end_date) : "";
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
