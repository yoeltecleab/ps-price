"use client";

import Link from "next/link";
import Image from "next/image";
import { Fire, TrendDown, Sparkle } from "@phosphor-icons/react";
import type { Game } from "@/lib/types";

export function MarketInsights({
  items,
  total,
  catalogTotal,
}: {
  items: Game[];
  total: number;
  catalogTotal?: number;
}) {
  if (!items.length) return null;

  const best = [...items].sort(
    (a, b) => (b.discount_percent ?? 0) - (a.discount_percent ?? 0),
  )[0];
  const biggestSave = [...items].sort(
    (a, b) => (b.savings_cents ?? 0) - (a.savings_cents ?? 0),
  )[0];
  const avgDiscount = Math.round(
    items.reduce((sum, g) => sum + (g.discount_percent ?? 0), 0) / items.length,
  );
  const underTen = items.filter(
    (g) => g.current_price_cents != null && g.current_price_cents <= 1000,
  ).length;

  return (
    <section className="grid gap-4 lg:grid-cols-12">
      {best ? (
        <Link
          href={`/games/${best.id}`}
          className="lg:col-span-7 relative overflow-hidden rounded-[var(--radius-xl)] holo-border holo-panel-strong p-6 md:p-8 block group transition-transform hover:scale-[1.01]"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-primary/20 via-transparent to-accent/10 pointer-events-none" />
          <div className="relative flex flex-col md:flex-row gap-6 items-start">
            <div className="relative size-28 shrink-0 rounded-[var(--radius-lg)] overflow-hidden border border-border-bright">
              {best.image_url ? (
                <Image src={best.image_url} alt="" fill className="object-cover" unoptimized />
              ) : null}
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-data text-[12px] uppercase tracking-[0.3em] text-accent flex items-center gap-2 mb-2">
                <Fire weight="fill" className="size-4" /> Steal of the cycle
              </p>
              <h2 className="font-display text-2xl md:text-3xl font-bold text-ink text-balance group-hover:text-accent transition-colors">
                {best.name}
              </h2>
              <div className="mt-4 flex flex-wrap items-baseline gap-3">
                <span className="font-display text-4xl font-bold text-glow-accent">
                  −{best.discount_percent ?? 0}%
                </span>
                <span className="font-data text-xl text-ink">{best.current_price_formatted}</span>
                {best.original_price_formatted ? (
                  <span className="font-data text-muted line-through">
                    {best.original_price_formatted}
                  </span>
                ) : null}
              </div>
              <span className="inline-flex mt-5 font-data text-xs uppercase tracking-widest text-accent">
                View intel →
              </span>
            </div>
          </div>
        </Link>
      ) : null}

      <div className="lg:col-span-5 grid grid-cols-2 gap-3">
        {[
          {
            icon: Sparkle,
            label: "Indexed deals",
            value: (catalogTotal ?? total).toLocaleString(),
          },
          {
            icon: TrendDown,
            label: "Avg discount",
            value: `${avgDiscount}%`,
          },
          {
            icon: Fire,
            label: "Under $10",
            value: String(underTen),
          },
          {
            icon: TrendDown,
            label: "Top savings",
            value: biggestSave?.savings_cents
              ? `$${(biggestSave.savings_cents / 100).toFixed(0)}`
              : "—",
          },
        ].map(({ icon: Icon, label, value }) => (
          <div
            key={label}
            className="holo-panel rounded-[var(--radius-lg)] p-4 flex flex-col justify-between min-h-[100px]"
          >
            <Icon className="size-5 text-accent mb-2" weight="duotone" />
            <div>
              <p className="font-display text-2xl font-bold text-ink tabular-nums">{value}</p>
              <p className="font-data text-[12px] uppercase tracking-widest text-muted mt-1">
                {label}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
