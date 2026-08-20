import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALPHAQUANT X",
  description: "DON'T CHASE TRADES. FIND QUALITY.",
};

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/scanner", label: "Live Scanner" },
  { href: "/playbooks", label: "Playbooks" },
  { href: "/strategy-lab", label: "Strategy Lab" },
  { href: "/health", label: "System Health" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-base-950 text-ink-100">
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r border-base-700 bg-base-900 px-4 py-6">
            <div className="mb-8">
              <div className="text-lg font-bold tracking-wide text-ink-100">
                ALPHA<span className="text-accent-teal">QUANT</span> X
              </div>
              <div className="mt-1 text-[10px] uppercase tracking-widest text-ink-500">
                Don&apos;t chase trades. Find quality.
              </div>
            </div>
            <nav className="flex flex-col gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded px-3 py-2 text-sm text-ink-300 transition-colors hover:bg-base-800 hover:text-ink-100"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="flex-1 px-8 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
