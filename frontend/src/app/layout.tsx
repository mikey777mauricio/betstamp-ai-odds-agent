import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Betstamp AI Odds Agent",
  description: "AI-powered odds analysis, anomaly detection, and daily market briefings",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-surface-secondary text-text-primary antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
