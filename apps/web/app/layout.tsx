import { GeistSans } from "geist/font/sans";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Desktop } from "@/components/desktop/desktop";
import { SessionGate } from "@/components/session";
import "./globals.css";
import { Providers } from "./providers";

const jetbrainsMono = localFont({
  src: "../node_modules/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2",
  variable: "--font-jetbrains-mono",
  weight: "100 800",
  display: "swap",
});

export const metadata: Metadata = {
  title: "KAIROS",
  description: "An operating system for your organization's AI: agents as processes, actions as governed syscalls, everything audited.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#07090c" };

/** Every route renders the desktop; the route itself only says which window is in front (see components/desktop). */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${jetbrainsMono.variable} h-full`} suppressHydrationWarning>
      <body className="h-full overflow-hidden">
        <Providers>
          <SessionGate>
            <Desktop />
          </SessionGate>
          {children}
        </Providers>
      </body>
    </html>
  );
}
