"use client";

import { useParams } from "next/navigation";
import { Conversation } from "@/components/trip/Conversation";

export default function TripPage() {
  const params = useParams<{ id: string }>();
  return <Conversation tripId={params.id} />;
}
