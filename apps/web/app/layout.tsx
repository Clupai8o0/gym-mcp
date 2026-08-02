import type { Metadata, Viewport } from "next";
import { Inter, Geist_Mono } from "next/font/google";

import { ServiceWorkerRegistrar } from "@/components/pwa/ServiceWorkerRegistrar";
import { THEME_BOOTSTRAP } from "@/lib/theme";
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
  // The SVG tab favicon scales everywhere; the PNGs cover install surfaces that ignore SVG
  // (Android home screen, iOS apple-touch — which won't render an SVG at all).
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: { capable: true, title: "Tempo", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  // Theme-aware chrome color (dark is the signature; light follows the token variant).
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
  ],
  colorScheme: "dark light",
  // Draw behind the iOS notch and home indicator; the shell's chrome carries the safe-area
  // insets itself (TabBar.module.css / (app)/layout.module.css).
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // `suppressHydrationWarning` covers exactly one attribute: the `data-theme` the bootstrap
    // below writes on <html> before React ever sees the document (lib/theme).
    <html lang="en" className={`${inter.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body>
        {/* First thing in the body, and blocking: the parser stops here, so a stored light/dark
            preference is on <html> before the first paint rather than one frame after it. This
            runs on the static routes too, which have no request context to read the cookie in. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        {children}
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
