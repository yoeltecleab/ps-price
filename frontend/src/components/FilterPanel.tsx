"use client";

import { Funnel, CaretDown, SortAscending, SortDescending } from "@phosphor-icons/react";
import { motion, AnimatePresence } from "motion/react";
import { useState } from "react";
import type { DealFilters, DealSort, SortDirection } from "@/lib/types";

const PLATFORMS = ["PS5", "PS4", "PS VR2", "PS VR"];

const SORT_OPTIONS: { value: DealSort; label: string }[] = [
  { value: "popularity", label: "Popularity" },
  { value: "discount", label: "Discount %" },
  { value: "savings", label: "Savings $" },
  { value: "savings_percent", label: "Savings %" },
  { value: "price", label: "Current price" },
  { value: "original", label: "Original price" },
  { value: "rating", label: "Rating" },
  { value: "name", label: "Name" },
  { value: "newest", label: "Recently synced" },
];

export function FilterPanel({
  filters,
  onChange,
  total,
}: {
  filters: DealFilters;
  onChange: (patch: Partial<DealFilters>) => void;
  total: number;
}) {
  const [expanded, setExpanded] = useState(true);
  const DirIcon = filters.sortDir === "asc" ? SortAscending : SortDescending;

  return (
    <div className="holo-panel rounded-[var(--radius-xl)] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-surface-raised/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Funnel className="size-4 text-accent" weight="fill" />
          <span className="font-display font-semibold text-sm text-ink">
            Filter matrix
          </span>
          <span className="font-data text-xs text-muted tabular-nums">
            {total.toLocaleString()} results
          </span>
        </div>
        <motion.span animate={{ rotate: expanded ? 180 : 0 }}>
          <CaretDown className="size-4 text-muted" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 space-y-5 border-t border-border/50">
              <div className="flex flex-wrap gap-2 pt-4">
                {PLATFORMS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() =>
                      onChange({ platform: filters.platform === p ? "" : p })
                    }
                    className={[
                      "h-9 px-4 rounded-full font-data text-xs uppercase tracking-wider border transition-all duration-200",
                      filters.platform === p
                        ? "bg-primary text-white border-primary shadow-[0_0_16px_var(--glow)]"
                        : "text-muted border-border hover:border-accent/50 hover:text-ink",
                    ].join(" ")}
                  >
                    {p}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => onChange({ onSaleOnly: !filters.onSaleOnly })}
                  className={[
                    "h-9 px-4 rounded-full font-data text-xs uppercase tracking-wider border transition-all",
                    filters.onSaleOnly
                      ? "bg-accent/20 text-accent border-accent/40"
                      : "text-muted border-border",
                  ].join(" ")}
                >
                  On sale
                </button>
              </div>

              <div>
                <p className="font-data text-[12px] uppercase tracking-widest text-muted mb-2">
                  Sort by
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex flex-wrap gap-2">
                    {SORT_OPTIONS.map((o) => (
                      <button
                        key={o.value}
                        type="button"
                        onClick={() => onChange({ sort: o.value })}
                        className={[
                          "h-8 px-3 rounded-[var(--radius-sm)] font-data text-xs transition-all",
                          filters.sort === o.value
                            ? "bg-surface-raised text-accent border border-accent/30"
                            : "text-muted hover:text-ink border border-transparent",
                        ].join(" ")}
                      >
                        {o.label}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      onChange({
                        sortDir: (filters.sortDir === "asc" ? "desc" : "asc") as SortDirection,
                      })
                    }
                    className="h-8 px-3 rounded-[var(--radius-sm)] font-data text-xs border border-border text-ink hover:border-accent/40 inline-flex items-center gap-1.5"
                    aria-label={`Sort direction: ${filters.sortDir}`}
                  >
                    <DirIcon className="size-4 text-accent" />
                    {filters.sortDir === "asc" ? "Ascending" : "Descending"}
                  </button>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="flex justify-between mb-2">
                    <label className="font-data text-xs uppercase tracking-wider text-muted">
                      Min discount
                    </label>
                    <span className="font-data text-xs text-accent tabular-nums">
                      {filters.minDiscount}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={90}
                    step={5}
                    value={filters.minDiscount}
                    onChange={(e) =>
                      onChange({ minDiscount: Number(e.target.value) })
                    }
                    className="w-full h-1 accent-accent bg-border rounded-full appearance-none cursor-pointer"
                  />
                </div>
                <div>
                  <label className="font-data text-xs uppercase tracking-wider text-muted mb-2 block">
                    Max price (USD)
                  </label>
                  <input
                    type="number"
                    min={0}
                    placeholder="∞"
                    value={filters.maxPrice}
                    onChange={(e) => onChange({ maxPrice: e.target.value })}
                    className="h-10 w-full rounded-[var(--radius-sm)] holo-panel px-3 font-data text-sm text-ink placeholder:text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                  />
                </div>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
