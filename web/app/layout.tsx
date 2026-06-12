import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "paper2md",
    template: "%s | paper2md",
  },
  description: "Math explanations for ArXiv papers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css"
        />
      </head>
      <body className="h-screen flex flex-col bg-zinc-50 text-zinc-900 antialiased overflow-hidden">
        <header className="bg-white border-b border-zinc-200 sticky top-0 z-10 shrink-0">
          <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight text-zinc-900">paper2md</span>
              <span className="hidden sm:inline text-xs bg-zinc-100 text-zinc-500 px-2 py-0.5 rounded-full font-medium">
                beta
              </span>
            </a>
            <nav className="flex items-center gap-4">
              <a href="/sat" className="text-sm font-medium text-zinc-500 hover:text-zinc-900 transition-colors">
                SAT Tutor
              </a>
              <span className="text-sm text-zinc-400 hidden sm:block">
                AI-explained equations
              </span>
            </nav>
          </div>
        </header>
        <main className="flex-1 min-h-0">{children}</main>
      </body>
    </html>
  );
}
