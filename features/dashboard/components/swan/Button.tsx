import Link from "next/link";

export function SwanButton({
  href,
  children,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link href={href} className={`swan-btn ${className}`.trim()}>
      {children}
    </Link>
  );
}
