"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowsClockwise, Lightning } from "@phosphor-icons/react";
import { motion } from "motion/react";
import { api } from "@/lib/api";
import type { DealFilters, DealsPage, Game } from "@/lib/types";
import { parseDollarsToCents } from "@/lib/format";
import { DealCard } from "@/components/DealCard";
import { FilterPanel } from "@/components/FilterPanel";
import { MarketInsights } from "@/components/MarketInsights";
import { BulkActionBar } from "@/components/BulkActionBar";
import { Button } from "@/components/Button";
import { Skeleton } from "@/components/Skeleton";
import { useTheme } from "@/components/ThemeProvider";

const defaultFilters: DealFilters = {
  q: "",
  platform: "",
  minDiscount: 0,
  maxPrice: "",
  sort: "popularity",
  sortDir: "asc",
  onSaleOnly: true,
};

export default function DealsHomePage() {
  const { theme } = useTheme();
  const [filters, setFilters] = useState<DealFilters>(defaultFilters);
  const [data, setData] = useState<DealsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<{
    catalog_total: number;
    fetched_count: string | null;
    last_sync: string | null;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [trackingId, setTrackingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkLibraryLoading, setBulkLibraryLoading] = useState(false);
  const [bulkWatchLoading, setBulkWatchLoading] = useState(false);
  const limit = 48;

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (filters.q.trim()) params.set("q", filters.q.trim());
    if (filters.platform) params.set("platform", filters.platform);
    if (filters.minDiscount > 0) params.set("min_discount", String(filters.minDiscount));
    const maxCents = parseDollarsToCents(filters.maxPrice);
    if (maxCents) params.set("max_price_cents", String(maxCents));
    params.set("sort", filters.sort);
    params.set("sort_dir", filters.sortDir);
    params.set("on_sale_only", filters.onSaleOnly ? "true" : "false");
    params.set("limit", String(limit));
    params.set("offset", String(page * limit));
    return params.toString();
  }, [filters, page]);

  const loadDeals = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<DealsPage>(`/api/deals?${queryString}`);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load deals");
    } finally {
      setLoading(false);
    }
  }, [queryString]);

  const pollSyncStatus = useCallback(async () => {
    try {
      const status = await api<{
        catalog_total: number;
        fetched_count: string | null;
        last_sync: string | null;
      }>("/api/sync-status");
      setSyncStatus(status);
      return status;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    void loadDeals();
  }, [loadDeals]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const status = await pollSyncStatus();
      if (cancelled) return;
      if (!status?.catalog_total) {
        setSyncing(true);
        try {
          await api("/api/sync-deals", { method: "POST" });
        } catch {
          /* background sync may already be running */
        }
        pollRef.current = setInterval(() => {
          void pollSyncStatus().then((s) => {
            if (s && s.catalog_total > 100) {
              setSyncing(false);
              if (pollRef.current) clearInterval(pollRef.current);
            }
          });
        }, 3000);
      }
    })();
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollSyncStatus]);

  useEffect(() => {
    setSelected(new Set());
  }, [page, queryString]);

  async function handleSync() {
    setSyncing(true);
    try {
      await api("/api/sync-deals", { method: "POST" });
      setPage(0);
      await pollSyncStatus();
      await loadDeals();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handleTrack(gameId: number) {
    setTrackingId(gameId);
    try {
      await api(`/api/games/${gameId}/track`, { method: "POST" });
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((g) =>
                g.id === gameId ? { ...g, is_tracked: true } : g,
              ),
            }
          : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to track");
    } finally {
      setTrackingId(null);
    }
  }

  function handleSelect(id: number, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function handleBulkLibrary() {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setBulkLibraryLoading(true);
    try {
      await api("/api/games/bulk-track", {
        method: "POST",
        body: JSON.stringify({ game_ids: ids }),
      });
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((g) =>
                ids.includes(g.id) ? { ...g, is_tracked: true } : g,
              ),
            }
          : prev,
      );
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk add failed");
    } finally {
      setBulkLibraryLoading(false);
    }
  }

  async function handleBulkWatch(email: string) {
    const ids = Array.from(selected);
    if (!ids.length || !email) return;
    setBulkWatchLoading(true);
    try {
      await api("/api/watches/bulk", {
        method: "POST",
        body: JSON.stringify({
          game_ids: ids,
          email,
          notify_on_any_drop: true,
          enabled: true,
          theme_id: theme,
        }),
      });
      await api("/api/games/bulk-track", {
        method: "POST",
        body: JSON.stringify({ game_ids: ids }),
      });
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((g) =>
                ids.includes(g.id) ? { ...g, is_tracked: true } : g,
              ),
            }
          : prev,
      );
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk watch failed");
    } finally {
      setBulkWatchLoading(false);
    }
  }

  const items = data?.items ?? [];
  const topDiscount = items.reduce(
    (max, g) => Math.max(max, g.discount_percent ?? 0),
    0,
  );

  return (
    <div className="space-y-10">
      <section className="relative pt-4 md:pt-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <p className="font-data text-xs uppercase tracking-[0.35em] text-accent mb-4">
            PlayStation Store · Neural feed
          </p>

          <h1 className="font-display text-[clamp(2.5rem,8vw,5rem)] font-extrabold leading-[0.95] tracking-[-0.03em] text-ink max-w-4xl">
            Hunt deals
            <br />
            <span className="text-glow-accent">before they vanish.</span>
          </h1>

          <p className="mt-6 text-base md:text-lg text-muted max-w-xl text-pretty leading-relaxed">
            Local catalog intelligence. Price history, predictive alerts,
            and filters no other tracker dares to ship.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
          className="mt-10 grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
        >
          {[
            { label: "Live deals", value: data?.total ?? syncStatus?.catalog_total ?? "—", glow: false },
            { label: "Peak cut", value: topDiscount ? `${topDiscount}%` : "—", glow: true },
            {
              label: "Feed status",
              value: syncing ? "SYNC" : data?.last_sync ? "ACTIVE" : "INIT",
              glow: false,
            },
            {
              label: "In catalog",
              value: syncStatus?.catalog_total?.toLocaleString() ?? "—",
              glow: false,
            },
          ].map((stat) => (
            <div
              key={stat.label}
              className="holo-panel-strong rounded-[var(--radius-lg)] p-4 md:p-5"
            >
              <p
                className={[
                  "font-data text-2xl md:text-3xl font-bold tabular-nums",
                  stat.glow ? "text-glow-accent" : "text-ink",
                ].join(" ")}
              >
                {stat.value}
              </p>
              <p className="font-data text-[12px] uppercase tracking-[0.2em] text-muted mt-2">
                {stat.label}
              </p>
            </div>
          ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mt-6 flex flex-wrap items-center gap-3"
        >
          <Button onClick={handleSync} loading={syncing} size="lg">
            <ArrowsClockwise className="size-4" weight="bold" />
            {syncing ? "Syncing 4,000+ deals…" : "Sync PlayStation feed"}
          </Button>
          {data?.last_sync ? (
            <span className="font-data text-xs text-muted flex items-center gap-1.5">
              <Lightning weight="fill" className="size-3.5 text-accent" />
              {new Date(data.last_sync).toLocaleString()}
            </span>
          ) : null}
        </motion.div>
      </section>

      {!loading && items.length > 0 ? (
        <MarketInsights
          items={items}
          total={data?.total ?? 0}
          catalogTotal={syncStatus?.catalog_total}
        />
      ) : null}

      <section className="space-y-4">
        <input
          type="search"
          value={filters.q}
          onChange={(e) => {
            setPage(0);
            setFilters((f) => ({ ...f, q: e.target.value }));
          }}
          placeholder="Query the deal matrix…"
          className="h-12 w-full rounded-[var(--radius-md)] holo-panel px-5 font-data text-sm text-ink placeholder:text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          aria-label="Filter deals by name"
        />
        <FilterPanel
          filters={filters}
          onChange={(patch) => {
            setPage(0);
            setFilters((f) => ({ ...f, ...patch }));
          }}
          total={data?.total ?? 0}
        />
      </section>

      {error ? (
        <div
          className="rounded-[var(--radius-md)] border border-error/40 bg-error/10 px-5 py-4 font-data text-sm text-error"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-80 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-24 holo-panel-strong rounded-[var(--radius-xl)]">
          <p className="font-display text-2xl font-bold text-ink">Signal lost</p>
          <p className="mt-3 text-muted max-w-sm mx-auto text-pretty">
            No deals match your filters. Sync the store or widen your search.
          </p>
          <Button className="mt-8" size="lg" onClick={handleSync} loading={syncing}>
            Initialize feed
          </Button>
        </div>
      ) : (
        <>
          <section>
            <h2 className="font-data text-xs uppercase tracking-[0.25em] text-muted mb-4">
              All deals
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
              {items.map((game, i) => (
                <DealCard
                  key={game.id}
                  game={game}
                  index={i}
                  onTrack={() => handleTrack(game.id)}
                  tracking={trackingId === game.id}
                  selected={selected.has(game.id)}
                  onSelect={handleSelect}
                />
              ))}
            </div>
          </section>

          <BulkActionBar
            count={selected.size}
            onAddToLibrary={handleBulkLibrary}
            onDeployWatch={handleBulkWatch}
            libraryLoading={bulkLibraryLoading}
            watchLoading={bulkWatchLoading}
          />

          {data && data.total > limit ? (
            <div className="flex justify-center items-center gap-4 pt-8">
              <Button
                variant="secondary"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                ← Prev
              </Button>
              <span className="font-data text-sm text-muted tabular-nums">
                {String(page + 1).padStart(2, "0")} /{" "}
                {String(Math.ceil(data.total / limit)).padStart(2, "0")}
              </span>
              <Button
                variant="secondary"
                disabled={(page + 1) * limit >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next →
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
