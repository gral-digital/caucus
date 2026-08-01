"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DOCS_NAV } from "@/app/docs/nav";
import { cn } from "@/lib/cn";

/** Nav laterale (desktop) della documentazione, con voce attiva evidenziata. */
export function DocsSidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {DOCS_NAV.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "rounded-lg px-3 py-2 text-[13.5px] transition",
              active
                ? "bg-paper text-ink font-medium"
                : "text-ink-muted hover:bg-paper-hover hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Nav orizzontale scrollabile (mobile). */
export function DocsMobileNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1.5 overflow-x-auto px-4 py-2 [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {DOCS_NAV.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 rounded-full border px-3 py-1.5 text-[12.5px] transition",
              active
                ? "border-ink bg-ink text-paper"
                : "border-paper-border bg-paper text-ink-muted hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
