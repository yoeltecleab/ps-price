"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Mail, Pencil, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Game, Watch } from "@/lib/types";
import { centsToDisplay, formatRelativeTime } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/Button";
import { Badge } from "@/components/Badge";
import { Skeleton } from "@/components/Skeleton";
import { WatchEditModal } from "@/components/WatchEditModal";

function ruleSummary(watch: Watch) {
  const parts: string[] = [];
  if (watch.target_price_cents) {
    parts.push(`Target ${centsToDisplay(watch.target_price_cents)}`);
  }
  if (watch.notify_on_any_drop) parts.push("Any drop");
  if (watch.min_drop_cents) {
    parts.push(`Min ${centsToDisplay(watch.min_drop_cents)} drop`);
  }
  if (watch.min_drop_percent) parts.push(`Min ${watch.min_drop_percent}% drop`);
  return parts.length ? parts : ["Default rules"];
}

export default function WatchesPage() {
  const { notificationEmails, refresh } = useAuth();
  const [watches, setWatches] = useState<Watch[]>([]);
  const [games, setGames] = useState<Map<number, Game>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Watch | null>(null);

  const load = useCallback(async () => {
    try {
      const [watchData, gameData] = await Promise.all([
        api<Watch[]>("/api/watches"),
        api<Game[]>("/api/games"),
      ]);
      setWatches(watchData);
      setGames(new Map(gameData.map((g) => [g.id, g])));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load watches");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleWatch(watch: Watch) {
    try {
      const updated = await api<Watch>(`/api/watches/${watch.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !watch.enabled }),
      });
      setWatches((prev) =>
        prev.map((w) => (w.id === watch.id ? updated : w)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function deleteWatch(id: number) {
    try {
      await api(`/api/watches/${id}`, { method: "DELETE" });
      setWatches((prev) => prev.filter((w) => w.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function testWatch(id: number) {
    setTestingId(id);
    try {
      await api(`/api/watches/${id}/test`, { method: "POST" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test email failed");
    } finally {
      setTestingId(null);
    }
  }

  return (
    <div>
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-ink">Price watches</h1>
        <p className="mt-1 text-sm text-muted">
          Email alerts when games hit your target price or drop.
        </p>
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
        <div className="grid gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : watches.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No watches yet"
          description="Open a tracked game and set a price alert to get notified by email."
          actionLabel="Go to library"
          actionHref="/"
        />
      ) : (
        <ul className="grid gap-3" role="list">
          {watches.map((watch) => {
            const game = games.get(watch.game_id);
            return (
              <li
                key={watch.id}
                className="p-4 rounded-[var(--radius-lg)] bg-surface border border-border animate-fade-in"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div className="min-w-0">
                    <Link
                      href={`/games/${watch.game_id}`}
                      className="text-sm font-semibold text-ink hover:text-accent transition-colors"
                    >
                      {game?.name ?? `Game #${watch.game_id}`}
                    </Link>
                    <p className="mt-1 text-xs text-muted">{watch.email}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {ruleSummary(watch).map((label) => (
                        <Badge key={label} variant={label.startsWith("Target") ? "accent" : "default"}>
                          {label}
                        </Badge>
                      ))}
                      <Badge variant={watch.enabled ? "success" : "default"}>
                        {watch.enabled ? "Active" : "Paused"}
                      </Badge>
                    </div>
                    {watch.last_notified_at ? (
                      <p className="mt-2 text-xs text-muted">
                        Last notified {formatRelativeTime(watch.last_notified_at)}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex gap-2 shrink-0 flex-wrap">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setEditing(watch)}
                    >
                      <Pencil className="size-3.5" aria-hidden />
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toggleWatch(watch)}
                    >
                      {watch.enabled ? "Pause" : "Enable"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => testWatch(watch.id)}
                      loading={testingId === watch.id}
                    >
                      <Mail className="size-3.5" aria-hidden />
                      Test
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteWatch(watch.id)}
                      aria-label="Delete watch"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {editing ? (
        <WatchEditModal
          watch={editing}
          notificationEmails={notificationEmails}
          onClose={() => setEditing(null)}
          onSaved={(updated) =>
            setWatches((prev) => prev.map((w) => (w.id === updated.id ? updated : w)))
          }
          onEmailsUpdated={refresh}
        />
      ) : null}
    </div>
  );
}
