import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Tempo",
  description: "Personal-first, share-ready workout app.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
