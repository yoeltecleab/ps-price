"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PriceHistoryEntry } from "@/lib/types";

interface ChartPoint {
  date: string;
  label: string;
  price: number;
}

export function PriceChart({ history }: { history: PriceHistoryEntry[] }) {
  const points: ChartPoint[] = history
    .filter((h) => h.price_cents !== null)
    .map((h) => ({
      date: h.checked_at,
      label: new Date(h.checked_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      }),
      price: h.price_cents! / 100,
    }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  if (points.length < 2) {
    return (
      <div className="flex h-52 items-center justify-center rounded-[var(--radius-lg)] border border-dashed border-border bg-surface/50">
        <p className="font-data text-sm text-muted text-center px-6">
          Price trajectory builds after multiple scans
        </p>
      </div>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="var(--color-border)"
            strokeDasharray="3 3"
            vertical={false}
          />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--color-muted)", fontSize: 12, fontFamily: "var(--font-data)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "var(--color-muted)", fontSize: 12, fontFamily: "var(--font-data)" }}
            axisLine={false}
            tickLine={false}
            width={48}
            tickFormatter={(v) => `$${v}`}
            domain={["dataMin - 2", "dataMax + 2"]}
          />
          <Tooltip
            contentStyle={{
              background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border-bright)",
              borderRadius: "var(--radius-md)",
              fontSize: "13px",
              fontFamily: "var(--font-data)",
            }}
            labelStyle={{ color: "var(--color-ink)" }}
            formatter={(value) => [`$${Number(value).toFixed(2)}`, "Price"]}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke="var(--color-accent)"
            strokeWidth={2}
            fill="url(#priceGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
