import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roam402",
  description: "An AI travel agent on a cryptographic leash — direct local bookings settled on the XRP Ledger.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
