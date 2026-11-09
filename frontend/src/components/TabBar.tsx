"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Today is active only at "/"; other tabs own their nested routes. */
export function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

const TABS = [
  { href: "/", label: "Today", path: "M5 7h14M5 12h14M5 17h7" },
  { href: "/alerts", label: "Alerts", path: "M3 17l5-6 4 3 4-7 5 6M3 21h18" },
  { href: "/research", label: "Research", path: "M6 3h9l3 3v15H6zM9 9h6M9 13h6M9 17h3" },
];

export function TabBar() {
  const pathname = usePathname() ?? "/";
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-rule bg-paper pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto flex max-w-[560px]">
        {TABS.map((t) => {
          const active = isActive(t.href, pathname);
          return (
            <li key={t.href} className="flex-1">
              <Link
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-caption ${
                  active ? "font-semibold text-pencil" : "text-ink-2"
                }`}
              >
                <svg
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={active ? 2.25 : 1.75}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d={t.path} />
                </svg>
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
