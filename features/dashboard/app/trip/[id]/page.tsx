"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Conversation } from "@/components/trip/Conversation";
import { ProposalWorkspace } from "@/components/trip/Proposal";
import { ReviewBook } from "@/components/trip/Review";

export default function TripPage() {
  const params = useParams<{ id: string }>();
  const [phase, setPhase] = useState<"talk" | "proposal" | "review">("talk");
  if (phase === "review") return <ReviewBook tripId={params.id} onBack={() => setPhase("proposal")} />;
  if (phase === "proposal") return <ProposalWorkspace tripId={params.id} onReview={() => setPhase("review")} />;
  return <Conversation tripId={params.id} onProposal={() => setPhase("proposal")} />;
}
