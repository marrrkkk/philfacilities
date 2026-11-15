import type { Metadata } from "next";
import { Archivo, Inter, Inter_Tight } from "next/font/google";
import { connection } from "next/server";

import { HydrationMarker } from "@/components/hydration-marker";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import "maplibre-gl/dist/maplibre-gl.css";

import "./globals.css";

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
});

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "PhilFacilities — Source-linked Philippine facilities data",
    template: "%s — PhilFacilities",
  },
  description:
    "An open, source-linked registry of Philippine schools and health facilities with provenance, geography, and measured data quality.",
  applicationName: "PhilFacilities",
  other: { license: "Apache-2.0 (code only; data rights vary by source)" },
  openGraph: {
    title: "PhilFacilities",
    description:
      "Search source-linked Philippine schools and health facilities, then inspect where every record came from.",
    type: "website",
  },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Nonce-based CSP requires dynamic rendering so every response gets a fresh
  // nonce attached to its scripts. Root-level connection() opts all routes in.
  await connection();

  return (
    <html lang="en-PH" className={`${interTight.variable} ${archivo.variable} ${inter.variable}`}>
      <body className="flex min-h-screen flex-col">
        <HydrationMarker />
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <SiteHeader />
        <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
