import type { Metadata, Viewport } from "next";
import { Inter, Geist_Mono } from "next/font/google";

import { ServiceWorkerRegistrar } from "@/components/pwa/ServiceWorkerRegistrar";
import "./globals.css";

// Inter is the documented open substitute for x.ai's proprietary Universal Sans (DESIGN.md);
// Geist Mono carries the uppercase tracked eyebrows/metrics. Both expose CSS variables that
// `design/tokens.css` reads via `--font-sans` / `--font-mono`.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Tempo",
    template: "%s · Tempo",
  },
  description:
    "Personal-first, share-ready workout app — an illustrated gym library, fast logging, and a progress dashboard.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  appleWebApp: { capable: true, title: "Tempo", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0a",
  colorScheme: "dark light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${geistMono.variable}`}>
      <body>
        {children}
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
