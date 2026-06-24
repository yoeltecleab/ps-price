"use client";

import { useCallback, useEffect, useState } from "react";
import { Books } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import type { Game } from "@/lib/types";
import { GameCard } from "@/components/GameCard";
import { GameCardSkeleton } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { BulkActionBar } from "@/components/BulkActionBar";
import { Button } from "@/components/Button";
import { useTheme } from "@/components/ThemeProvider";
import { useAuth } from "@/lib/auth";
import { refreshCatalogPrices } from "@/lib/catalogRefresh";

export default function LibraryPage() {
  const { theme } = useTheme();
  const { user, loading: authLoading, requireVerified, notificationEmails, refresh } = useAuth();
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkWatchLoading, setBulkWatchLoading] = useState(false);

  const loadGames = useCallback(async () => {
    try {
      const data = await api<Game[]>("/api/games");
      setGames(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load library");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user?.email_verified) {
      requireVerified("/library");
      setLoading(false);
      return;
    }
    void loadGames();
  }, [authLoading, user, loadGames, requireVerified]);

  async function handleDelete(id: number) {
    try {
      await api(`/api/games/${id}`, { method: "DELETE" });
      setGames((prev) => prev.filter((g) => g.id !== id));
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function handleRefreshAll() {
    setRefreshingAll(true);
    try {
      const result = await refreshCatalogPrices();
      if (result.message) setError(null);
      await loadGames();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshingAll(false);
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

  async function handleBulkWatch(notificationEmailId: number) {
    if (!requireVerified("/library")) return;
    const ids = Array.from(selected);
    if (!ids.length || !notificationEmailId) return;
    setBulkWatchLoading(true);
    try {
      await api("/api/watches/bulk", {
        method: "POST",
        body: JSON.stringify({
          game_ids: ids,
          notification_email_id: notificationEmailId,
          notify_on_any_drop: true,
          enabled: true,
          theme_id: theme,
        }),
      });
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk watch failed");
    } finally {
      setBulkWatchLoading(false);
    }
  }

  return (
    <div>
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-ink">Your library</h1>
          <p className="mt-1 text-sm text-muted">
            {games.length} tracked game{games.length !== 1 ? "s" : ""}
          </p>
        </div>
        {games.length > 0 ? (
          <Button variant="secondary" onClick={handleRefreshAll} loading={refreshingAll}>
            Sync prices
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          className="mb-4 rounded-[var(--radius-md)] border border-error/30 bg-error/10 px-4 py-3 text-sm text-error"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="grid gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <GameCardSkeleton key={i} />
          ))}
        </div>
      ) : games.length === 0 ? (
        <EmptyState
          icon={Books}
          title="Library empty"
          description="Select deals from the feed and add them to your library."
          actionLabel="Open deal feed"
          actionHref="/"
        />
      ) : (
        <>
          <div className="grid gap-4">
            {games.map((game) => (
              <GameCard
                key={game.id}
                game={game}
                onDelete={() => handleDelete(game.id)}
                selected={selected.has(game.id)}
                onSelect={handleSelect}
              />
            ))}
          </div>
          <BulkActionBar
            count={selected.size}
            showLibrary={false}
            onDeployWatch={handleBulkWatch}
            watchLoading={bulkWatchLoading}
            notificationEmails={notificationEmails}
            onEmailsUpdated={refresh}
          />
        </>
      )}
    </div>
  );
}
