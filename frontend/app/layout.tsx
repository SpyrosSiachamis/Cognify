import type { Metadata, Viewport } from "next";
import { Fraunces, Hanken_Grotesk, JetBrains_Mono, Newsreader } from "next/font/google";
import "./globals.css";

// The four type families from the prototype. Each sets a CSS variable that globals.css uses.
const fraunces = Fraunces({ subsets: ["latin"], axes: ["opsz"], style: ["normal", "italic"], variable: "--font-fraunces", display: "swap" });
const newsreader = Newsreader({ subsets: ["latin"], axes: ["opsz"], style: ["normal", "italic"], variable: "--font-newsreader", display: "swap" });
const hanken = Hanken_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-hanken", display: "swap" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "Cognify",
  description: "Solve it. Then prove it.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

// Runs before the page paints, so a saved Salon theme never flashes Velvet first.
const themeScript = `try{if(localStorage.getItem('cognify-theme')==='salon')document.documentElement.setAttribute('data-theme','salon')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${newsreader.variable} ${hanken.variable} ${jetbrains.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
