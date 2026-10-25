import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Swanavi",
  description: "Swanavi plans the trip. A cryptographic leash settles the local bookings on the XRP Ledger.",
  manifest: "/manifest.webmanifest",
  icons: { icon: ["/icon.svg", "/favicon.ico"], apple: "/icon-192.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
