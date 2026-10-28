import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "NEXUS QUANT", template: "%s · NEXUS QUANT" },
  description: "Crypto backtesting, strategy discovery, journal and paper trading. Analysis and simulation only.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
