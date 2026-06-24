"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";
import type { AdminOverview } from "@/lib/adminTypes";
import {
  badgeClass,
  badgeStats,
  computeAdminBadges,
  type AdminBadge,
  type BadgeTier,
} from "@/lib/adminBadges";

const tiers: BadgeTier[] = ["neon", "platinum", "gold", "silver", "bronze"];
const categories = [
  "All",
  "Command",
  "Milestones",
  "Catalog",
  "Users",
  "Security",
  "Alerts",
  "Email",
  "Ops",
  "Intel",
  "Deals",
  "Service Record",
];

function BadgePill({ badge, compact }: { badge: AdminBadge; compact?: boolean }) {
  return (
    <motion.div
      layout
      title={`${badge.title} — ${badge.description}`}
      className={[
        "group relative flex flex-col items-center justify-center rounded-full border text-center transition-transform hover:scale-105",
        compact ? "size-14 sm:size-16" : "size-16 sm:size-[4.5rem]",
        badgeClass(badge.tier, badge.earned),
      ].join(" ")}
    >
      <span className={compact ? "text-lg" : "text-xl sm:text-2xl"}>{badge.emoji}</span>
      {!compact ? (
        <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 w-max max-w-[5rem] truncate font-data text-[9px] uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity">
          {badge.title}
        </span>
      ) : null}
    </motion.div>
  );
}

export function AdminBadgeWall({
  overview,
  adminName,
}: {
  overview: AdminOverview | null;
  adminName: string;
}) {
  const badges = useMemo(() => computeAdminBadges(overview), [overview]);
  const stats = badgeStats(badges);
  const [category, setCategory] = useState("All");
  const [earnedOnly, setEarnedOnly] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const featured = badges.filter((b) => !b.id.startsWith("filler-") && b.earned);
  const filtered = badges.filter((b) => {
    if (earnedOnly && !b.earned) return false;
    if (category !== "All" && b.category !== category) return false;
    return true;
  });
  const display = showAll ? filtered : filtered.slice(0, 180);
  const hidden = filtered.length - display.length;

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden holo-panel-strong rounded-[var(--radius-xl)] p-6 md:p-8">
        <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-primary/10 pointer-events-none" />
        <div className="relative flex flex-col lg:flex-row gap-8 items-start">
          <div className="relative shrink-0 mx-auto lg:mx-0">
            <div className="size-36 md:size-44 rounded-full border-2 border-accent/40 bg-surface/60 flex items-center justify-center relative overflow-visible">
              <span className="font-display text-4xl font-black text-accent">
                {adminName.charAt(0).toUpperCase()}
              </span>
              <div className="absolute inset-0 -m-3 pointer-events-none">
                {featured.slice(0, 24).map((badge, i) => {
                  const angle = (i / 24) * Math.PI * 2;
                  const r = 78;
                  const x = 50 + Math.cos(angle) * (r / 1.8);
                  const y = 50 + Math.sin(angle) * (r / 1.8);
                  return (
                    <div
                      key={badge.id}
                      className="absolute size-7 -translate-x-1/2 -translate-y-1/2"
                      style={{ left: `${x}%`, top: `${y}%` }}
                    >
                      <BadgePill badge={badge} compact />
                    </div>
                  );
                })}
              </div>
            </div>
            <p className="text-center mt-4 font-data text-[10px] uppercase tracking-[0.3em] text-accent">
              Field Marshal
            </p>
          </div>

          <div className="flex-1 space-y-4 min-w-0">
            <div>
              <p className="font-data text-xs uppercase tracking-[0.35em] text-muted">Insignia record</p>
              <h2 className="font-display text-3xl md:text-4xl font-extrabold text-ink tracking-tight">
                {stats.earned.toLocaleString()} badges earned
              </h2>
              <p className="text-sm text-muted mt-1">
                {adminName} — uniform capacity {stats.total.toLocaleString()} · every admin power is a badge
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {tiers.map((tier) => {
                const count = badges.filter((b) => b.tier === tier && b.earned).length;
                return (
                  <span
                    key={tier}
                    className={[
                      "font-data text-[10px] uppercase tracking-widest px-2.5 py-1 rounded-full border",
                      badgeClass(tier, count > 0),
                    ].join(" ")}
                  >
                    {tier} · {count}
                  </span>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-3 pt-1">
              <label className="flex items-center gap-2 font-data text-xs text-muted">
                <input
                  type="checkbox"
                  checked={earnedOnly}
                  onChange={(e) => setEarnedOnly(e.target.checked)}
                />
                Earned only
              </label>
              {!showAll && hidden > 0 ? (
                <button
                  type="button"
                  onClick={() => setShowAll(true)}
                  className="font-data text-xs text-accent hover:underline"
                >
                  Show all {filtered.length.toLocaleString()} badges
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategory(cat)}
            className={[
              "font-data text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-full border transition-colors",
              category === cat
                ? "border-accent/50 text-accent bg-accent/10"
                : "border-border/50 text-muted hover:text-ink",
            ].join(" ")}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 sm:gap-3">
        {display.map((badge) => (
          <BadgePill key={badge.id} badge={badge} />
        ))}
      </div>
      {hidden > 0 && !showAll ? (
        <p className="font-data text-xs text-muted text-center">
          + {hidden.toLocaleString()} more badges on your uniform — show all to inspect
        </p>
      ) : null}
    </div>
  );
}
