"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Suspense, useState } from "react";

import { useAuth } from "./auth";
import { cx, Skeleton } from "./ui";

export const NAV = [
  { href: "/", label: "Overview", icon: "M3 12l9-8 9 8M5 10v10h14V10" },
  { href: "/discover", label: "Discover", icon: "M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-4.3-4.3" },
  { href: "/strategies", label: "Strategy Lab", icon: "M9 3h6M10 3v6L4 19a1 1 0 001 2h14a1 1 0 001-2l-6-10V3" },
  { href: "/journal", label: "Journal", icon: "M5 4h11l3 3v13H5zM9 9h6M9 13h6M9 17h4" },
  { href: "/paper", label: "Paper Trading", icon: "M4 19h16M6 16l4-5 3 3 5-7" },
  { href: "/ai", label: "AI Research", icon: "M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2M12 8a4 4 0 100 8 4 4 0 000-8z" },
  { href: "/settings", label: "Settings", icon: "M12 9a3 3 0 100 6 3 3 0 000-6zM19 12a7 7 0 00-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 00-2-1.2L14 3h-4l-.5 2.6a7 7 0 00-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 002 1.2L10 21h4l.5-2.6a7 7 0 002-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {NAV.map((n) => {
        const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
        return (
          <li key={n.href}>
            <Link
              href={n.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cx(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                active ? "bg-raised text-fg" : "text-fg-muted hover:bg-raised/60 hover:text-fg",
              )}
            >
              <Icon d={n.icon} />
              {n.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function StaticNav() {
  return (
    <ul className="space-y-0.5">
      {NAV.map((n) => (
        <li key={n.href}>
          <Link href={n.href} className="flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-fg-muted hover:bg-raised/60 hover:text-fg">
            <Icon d={n.icon} />
            {n.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 px-2.5 py-1">
      <span aria-hidden className="grid size-6 place-items-center rounded-sm bg-accent text-[11px] font-bold text-[#06231a]">
        NQ
      </span>
      <span className="text-[13px] font-semibold tracking-wide">NEXUS QUANT</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-panel focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className={cx("fixed inset-y-0 left-0 z-40 w-56 border-r border-line bg-panel px-2 py-3 transition-transform md:static md:translate-x-0", open ? "translate-x-0" : "-translate-x-full")}>
        <Brand />
        <nav aria-label="Main" className="mt-4">
          <Suspense fallback={<StaticNav />}>
            <NavLinks onNavigate={() => setOpen(false)} />
          </Suspense>
        </nav>
        <div className="absolute inset-x-2 bottom-3 space-y-2">
          <div className="rounded-md border border-line bg-panel-2 px-2.5 py-2 text-[11px] leading-snug text-fg-faint">
            Analysis and simulation only. No real orders. Past results do not predict future returns.
          </div>
        </div>
      </aside>
      {open && <button type="button" aria-label="Close menu" className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur">
          <button type="button" className="rounded-md p-1.5 text-fg-muted hover:bg-raised md:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Icon d="M4 6h16M4 12h16M4 18h16" />
          </button>
          <div className="hidden text-xs text-fg-faint md:block">Crypto backtesting · BTC & ETH · UTC</div>
          <div className="flex items-center gap-3 text-[13px]">
            {loading ? <Skeleton className="h-5 w-40" /> : user ? <span className="text-fg-muted">{user.email}</span> : null}
            {user && (
              <button type="button" onClick={() => void logout()} className="rounded-md px-2 py-1 text-fg-muted hover:bg-raised hover:text-fg">
                Sign out
              </button>
            )}
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6">
          {loading || !user ? (
            <div className="space-y-3">
              <Skeleton className="h-7 w-56" />
              <Skeleton className="h-32" />
              <Skeleton className="h-64" />
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
