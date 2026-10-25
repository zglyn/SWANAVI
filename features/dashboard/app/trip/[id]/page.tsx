"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Conversation } from "@/components/trip/Conversation";
import { ProposalWorkspace } from "@/components/trip/Proposal";

export default function TripPage() {
  const params = useParams<{ id: string }>();
  const [phase, setPhase] = useState<"talk" | "proposal">("talk");
  if (phase === "proposal") return <ProposalWorkspace tripId={params.id} />;
  return <Conversation tripId={params.id} onProposal={() => setPhase("proposal")} />;
}
