import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cognify",
  description: "Solve it. Then prove it.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

// Runs before the page paints, so a saved Salon theme never flashes Velvet first.
const themeScript = `try{if(localStorage.getItem('cognify-theme')==='salon')document.documentElement.setAttribute('data-theme','salon')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        {/* Load the main fonts early so text does not jump when they arrive. */}
        <link rel="preload" href="/fonts/Fraunces-italic-latin-feced2.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/Fraunces-normal-latin-39ce20.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/HankenGrotesk-normal-latin-605034.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/Newsreader-normal-latin-b76914.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
