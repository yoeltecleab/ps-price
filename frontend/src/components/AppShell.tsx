"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, House, Pulse, Books, Shield } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { GlobalSearch } from "./GlobalSearch";
import { Scene } from "./Scene";
import { SettingsDrawer } from "./SettingsDrawer";
import { AuthMenu } from "./AuthMenu";
import { useAuth } from "@/lib/auth";
import { KeyboardHelp } from "./KeyboardHelp";
import Image from "next/image";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();

  const navItems = [
    { href: "/", label: "Deals", icon: House },
    { href: "/library", label: "Library", icon: Books },
    { href: "/watches", label: "Alerts", icon: Bell },
    { href: "/notifications", label: "Feed", icon: Pulse },
    ...(user?.is_admin
      ? [{ href: "/admin", label: "Admin", icon: Shield }]
      : []),
  ];

  return (
    <div className="relative min-h-dvh">
      <Scene />

      <header className="sticky top-0 z-[100] border-b border-border/60 holo-panel-strong">
        <div className="max-w-7xl mx-auto px-4 md:px-8">
          {/* Brand row */}
          <div className="flex items-center gap-4 py-3 border-b border-border/40">
            <Link href="/" className="flex items-center gap-3 shrink-0 group">
              <div className="relative flex size-10 items-center justify-center">
                <div className="absolute inset-0 rounded-[var(--radius-md)] bg-primary opacity-80 blur-md group-hover:opacity-100 transition-opacity" />
                <div className="relative flex size-10 items-center justify-center rounded-[var(--radius-md)] bg-surface border border-accent/40 overflow-hidden">
                  <Image src="/icon.svg" alt="" width={40} height={40} className="size-full" />
                </div>
              </div>
              <div className="hidden sm:block">
                <p className="font-display font-bold text-sm text-ink tracking-tight leading-none">
                  PS PRICE
                </p>
                <p className="font-data text-[13px] uppercase tracking-[0.25em] text-accent mt-0.5">
                  2050
                </p>
              </div>
            </Link>

            <div className="flex-1 max-w-2xl mx-auto">
              <GlobalSearch />
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <AuthMenu />
              <SettingsDrawer />
            </div>
          </div>

          {/* Top navigation */}
          <nav
            className="flex items-center gap-1 py-2 overflow-x-auto"
            aria-label="Main navigation"
          >
            {navItems.map(({ href, label, icon: Icon }) => {
              const active =
                pathname === href || (href !== "/" && pathname.startsWith(href));
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    "relative flex items-center gap-2 px-4 py-2 rounded-[var(--radius-md)] font-data text-xs uppercase tracking-wider whitespace-nowrap transition-colors",
                    active
                      ? "text-accent"
                      : "text-muted hover:text-ink hover:bg-surface/50",
                  ].join(" ")}
                  aria-current={active ? "page" : undefined}
                >
                  {active ? (
                    <motion.div
                      layoutId="top-nav-indicator"
                      className="absolute inset-0 rounded-[var(--radius-md)] bg-primary/15 border border-accent/20 -z-10"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  ) : null}
                  <Icon className="size-4" weight={active ? "fill" : "regular"} />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="relative z-10 px-4 md:px-8 py-8 pb-16 max-w-7xl mx-auto">
        {children}
      </main>
      <KeyboardHelp />
    </div>
  );
}
