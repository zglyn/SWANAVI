import { redirect } from "next/navigation";

export default async function PlanRoot({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/plan/${id}/overview`);
}
