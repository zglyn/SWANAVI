import { SwanMark } from "@/components/brand/SwanMark";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 text-xl font-bold tracking-tight ${className}`}>
      <SwanMark />
      <span>Swanavi</span>
    </span>
  );
}
