import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Heagent — AI Employee Dashboard",
  description: "Autonomous AI Employee — Bronze/Silver/Gold Tier Control Panel",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#050B18",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-heagent-void text-slate-100 antialiased" style={{ fontFamily: "var(--font-inter, system-ui, sans-serif)" }}>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
