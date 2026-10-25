import type { Metadata } from "next";
import { Fraunces, Outfit } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-fraunces",
});

const outfit = Outfit({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-outfit",
});

export const metadata: Metadata = {
  title: "Swanavi",
  description: "Swanavi plans the trip. A cryptographic leash settles the local bookings on the XRP Ledger.",
  manifest: "/manifest.webmanifest",
  icons: { icon: ["/icon.svg", "/favicon.ico"], apple: "/icon-192.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${outfit.variable}`}>
      <body className={outfit.className}>{children}</body>
    </html>
  );
}
