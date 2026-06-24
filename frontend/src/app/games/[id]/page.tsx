"use client";

import { use, useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowsClockwise,
  ArrowSquareOut,
  Bell,
  BookmarkSimple,
  ChartLineUp,
  GameController,
  Tag,
} from "@phosphor-icons/react";
import { motion } from "motion/react";
import { api } from "@/lib/api";
import type { GameDetail, Watch } from "@/lib/types";
import { formatDateTime, parseDollarsToCents } from "@/lib/format";
import { PriceChart } from "@/components/PriceChart";
import { AlertEmailSelect } from "@/components/AlertEmailSelect";
import { WatchAlertFields } from "@/components/WatchAlertFields";
import { Button } from "@/components/Button";
import { GameCardSkeleton } from "@/components/Skeleton";
import { ConfettiBurst } from "@/components/ConfettiBurst";
import { useTheme } from "@/components/ThemeProvider";
import { useAuth, useVerifiedEmails } from "@/lib/auth";

export default function GameDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { theme } = useTheme();
  const { requireVerified, notificationEmails, refresh } = useAuth();
  const verifiedEmails = useVerifiedEmails();
  const { id: idStr } = use(params);
  const gameId = Number(idStr);
  const [game, setGame] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notificationEmailId, setNotificationEmailId] = useState<number | "">("");
  const [targetPrice, setTargetPrice] = useState("");
  const [notifyAnyDrop, setNotifyAnyDrop] = useState(true);
  const [minDropDollars, setMinDropDollars] = useState("");
  const [minDropPercent, setMinDropPercent] = useState("");
  const [creatingWatch, setCreatingWatch] = useState(false);
  const [watchSuccess, setWatchSuccess] = useState(false);
  const [confetti, setConfetti] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);

  const loadGame = useCallback(async () => {
    if (!gameId || Number.isNaN(gameId)) return;
    try {
      const data = await api<GameDetail>(`/api/games/${gameId}`);
      setGame(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load game");
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    loadGame();
  }, [loadGame]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshNotice(null);
    try {
      const updated = await api<GameDetail>(`/api/games/${gameId}/refresh`, { method: "POST" });
      setGame((prev) => (prev ? { ...prev, ...updated, history: prev.history } : updated));
      setRefreshNotice("Game details refreshed from PlayStation Store.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const primary = verifiedEmails.find((e) => e.is_primary) ?? verifiedEmails[0];
    if (primary) setNotificationEmailId(primary.id);
  }, [verifiedEmails]);

  async function handleAddToLibrary() {
    if (!requireVerified()) return;
    if (!gameId) return;
    setTracking(true);
    try {
      const updated = await api<GameDetail>(`/api/games/${gameId}/track`, { method: "POST" });
      setGame((prev) => (prev ? { ...prev, ...updated, history: prev.history } : prev));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add to library");
    } finally {
      setTracking(false);
    }
  }

  async function handleCreateWatch(e: React.FormEvent) {
    e.preventDefault();
    if (!requireVerified()) return;
    if (!gameId || !notificationEmailId) return;
    setCreatingWatch(true);
    setWatchSuccess(false);
    try {
      if (!game?.is_tracked) {
        await api(`/api/games/${gameId}/track`, { method: "POST" });
      }
      const cents = parseDollarsToCents(targetPrice);
      await api<Watch>("/api/watches", {
        method: "POST",
        body: JSON.stringify({
          game_id: gameId,
          notification_email_id: notificationEmailId,
          target_price_cents: cents,
          notify_on_any_drop: notifyAnyDrop,
          min_drop_cents: parseDollarsToCents(minDropDollars),
          min_drop_percent: minDropPercent ? Number(minDropPercent) : null,
          enabled: true,
          theme_id: theme,
        }),
      });
      setWatchSuccess(true);
      setConfetti(true);
      setTargetPrice("");
      await loadGame();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create watch");
    } finally {
      setCreatingWatch(false);
    }
  }

  if (loading) {
    return (
      <div className="pt-8">
        <GameCardSkeleton />
      </div>
    );
  }

  if (!game) {
    return (
      <div className="text-center py-24 holo-panel-strong rounded-[var(--radius-xl)]">
        <GameController className="size-12 mx-auto text-muted mb-4" />
        <p className="font-display text-2xl font-bold text-ink">Signal not found</p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-2 font-data text-sm text-accent hover:underline"
        >
          <ArrowLeft className="size-4" />
          Back to deals
        </Link>
      </div>
    );
  }

  const onSale =
    game.original_price_cents != null &&
    game.current_price_cents != null &&
    game.original_price_cents > game.current_price_cents;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="space-y-8 pb-12"
    >
      <ConfettiBurst active={confetti} />

      <Link
        href="/"
        className="inline-flex items-center gap-2 font-data text-xs uppercase tracking-widest text-muted hover:text-accent transition-colors"
      >
        <ArrowLeft className="size-4" />
        Deals matrix
      </Link>

      {error ? (
        <div
          className="rounded-[var(--radius-md)] border border-error/40 bg-error/10 px-5 py-4 font-data text-sm text-error"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <section className="relative overflow-hidden rounded-[var(--radius-xl)] holo-panel-strong">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-accent/5 pointer-events-none" />
        <div className="relative flex flex-col lg:flex-row gap-8 p-6 md:p-10">
          <div className="relative shrink-0 mx-auto lg:mx-0">
            <div className="absolute -inset-2 rounded-[var(--radius-lg)] bg-accent/20 blur-xl" />
            <div className="relative size-40 md:size-48 rounded-[var(--radius-lg)] overflow-hidden border border-border-bright shadow-2xl">
              {game.image_url ? (
                <Image
                  src={game.image_url}
                  alt=""
                  width={192}
                  height={192}
                  className="object-cover size-full"
                  unoptimized
                  priority
                />
              ) : (
                <div className="size-full bg-surface-raised flex items-center justify-center">
                  <GameController className="size-16 text-muted" />
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 min-w-0 text-center lg:text-left">
            <p className="font-data text-[12px] uppercase tracking-[0.3em] text-accent mb-3">
              Product intel
            </p>
            <h1 className="font-display text-3xl md:text-4xl font-extrabold text-ink tracking-tight text-balance">
              {game.name}
            </h1>
            <p className="mt-2 font-data text-xs text-muted">{game.product_id}</p>

            {game.genres?.length ? (
              <div className="mt-3 flex flex-wrap justify-center lg:justify-start gap-2">
                {game.genres.map((g) => (
                  <span
                    key={g}
                    className="font-data text-[12px] uppercase tracking-wider px-2.5 py-1 rounded-full border border-accent/30 text-accent"
                  >
                    {g}
                  </span>
                ))}
              </div>
            ) : null}

            <div className="mt-8 flex flex-wrap items-end justify-center lg:justify-start gap-4">
              <div>
                <p className="font-data text-[12px] uppercase tracking-widest text-muted mb-1">
                  Current price
                </p>
                <p className="font-display text-4xl md:text-5xl font-bold tabular-nums text-glow-accent">
                  {game.current_price_formatted ?? "—"}
                </p>
              </div>
              {onSale && game.original_price_formatted ? (
                <div>
                  <p className="font-data text-[12px] uppercase tracking-widest text-muted mb-1">
                    Was
                  </p>
                  <p className="font-data text-xl text-muted line-through tabular-nums">
                    {game.original_price_formatted}
                  </p>
                </div>
              ) : null}
              {game.discount_percent ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/15 border border-accent/30 font-data text-sm font-bold text-accent">
                  <Tag weight="fill" className="size-4" />
                  −{game.discount_percent}%
                </span>
              ) : null}
            </div>

            <div className="mt-8 flex flex-wrap justify-center lg:justify-start gap-3">
              {!game.is_tracked ? (
                <Button onClick={handleAddToLibrary} loading={tracking} size="lg">
                  <BookmarkSimple className="size-4" weight="fill" />
                  Add to library
                </Button>
              ) : null}
              <Button onClick={handleRefresh} loading={refreshing} size="lg" variant="secondary">
                <ArrowsClockwise className="size-4" weight="bold" />
                Refresh signal
              </Button>
              <a
                href={game.store_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-12 items-center gap-2 px-5 rounded-[var(--radius-md)] holo-panel font-data text-sm text-ink hover:text-accent transition-colors"
              >
                <ArrowSquareOut className="size-4" />
                Open in PS Store
              </a>
            </div>

            <p className="mt-4 font-data text-[13px] text-muted">
              Last scan {formatDateTime(game.last_checked_at)}
              {game.availability ? <span className="mx-2 text-border">·</span> : null}
              {game.availability}
            </p>
            {refreshNotice ? (
              <p className="mt-2 font-data text-xs text-accent">{refreshNotice}</p>
            ) : null}
          </div>
        </div>
      </section>

      {(game.description_short ||
        game.description_long ||
        game.publisher ||
        game.release_date ||
        game.rating_average ||
        game.features?.length ||
        game.screenshots?.length) && (
        <section className="holo-panel rounded-[var(--radius-xl)] p-6 md:p-8 space-y-6">
          {game.description_short || game.description_long ? (
            <div>
              <h2 className="font-display text-lg font-bold text-ink mb-3">About</h2>
              {game.description_short ? (
                <p className="font-display text-base text-accent mb-3">{game.description_short}</p>
              ) : null}
              {game.description_long ? (
                <p className="text-sm text-muted leading-relaxed text-pretty whitespace-pre-line">
                  {game.description_long}
                </p>
              ) : null}
            </div>
          ) : null}

          {(game.publisher || game.release_date || game.rating_average) && (
            <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-data text-sm">
              {game.publisher ? (
                <div>
                  <dt className="text-xs uppercase tracking-widest text-muted">Publisher</dt>
                  <dd className="mt-1 text-ink">{game.publisher}</dd>
                </div>
              ) : null}
              {game.release_date ? (
                <div>
                  <dt className="text-xs uppercase tracking-widest text-muted">Release</dt>
                  <dd className="mt-1 text-ink">{game.release_date}</dd>
                </div>
              ) : null}
              {game.rating_average ? (
                <div>
                  <dt className="text-xs uppercase tracking-widest text-muted">Rating</dt>
                  <dd className="mt-1 text-ink">
                    {game.rating_average.toFixed(1)}
                    {game.rating_count ? ` (${game.rating_count.toLocaleString()})` : ""}
                  </dd>
                </div>
              ) : null}
            </dl>
          )}

          {game.features?.length ? (
            <div>
              <h3 className="font-data text-xs uppercase tracking-widest text-muted mb-3">Features</h3>
              <ul className="flex flex-wrap gap-2">
                {game.features.map((feature) => (
                  <li
                    key={feature}
                    className="font-data text-xs px-2.5 py-1 rounded-full border border-border text-muted"
                  >
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {game.screenshots?.length ? (
            <div>
              <h3 className="font-data text-xs uppercase tracking-widest text-muted mb-3">Screenshots</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {game.screenshots.map((url) => (
                  <a
                    key={url}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="relative aspect-video overflow-hidden rounded-[var(--radius-md)] border border-border bg-surface-raised"
                  >
                    <Image
                      src={url}
                      alt=""
                      fill
                      className="object-cover hover:scale-105 transition-transform duration-300"
                      unoptimized
                      sizes="(max-width: 768px) 100vw, 33vw"
                    />
                  </a>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <section className="xl:col-span-8 holo-panel rounded-[var(--radius-xl)] p-6 md:p-8">
          <div className="flex items-center gap-3 mb-6">
            <ChartLineUp className="size-5 text-accent" weight="duotone" />
            <h2 className="font-display text-lg font-bold text-ink">Price trajectory</h2>
          </div>
          <PriceChart history={game.history} />
        </section>

        <aside className="xl:col-span-4">
          <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6 md:p-8 sticky top-28">
            <div className="flex items-center gap-3 mb-2">
              <Bell className="size-5 text-accent" weight="duotone" />
              <h2 className="font-display text-lg font-bold text-ink">Price alert</h2>
            </div>
            <p className="font-data text-xs text-muted text-pretty leading-relaxed">
              Deploy a watch after adding this title to your library. All watches live in library first.
            </p>

            <form onSubmit={handleCreateWatch} className="mt-6 flex flex-col gap-4">
              <AlertEmailSelect
                emails={notificationEmails}
                value={notificationEmailId}
                onChange={setNotificationEmailId}
                onEmailsUpdated={refresh}
              />
              {verifiedEmails.length ? (
                <WatchAlertFields
                  targetPrice={targetPrice}
                  onTargetPriceChange={setTargetPrice}
                  notifyAnyDrop={notifyAnyDrop}
                  onNotifyAnyDropChange={setNotifyAnyDrop}
                  minDropDollars={minDropDollars}
                  onMinDropDollarsChange={setMinDropDollars}
                  minDropPercent={minDropPercent}
                  onMinDropPercentChange={setMinDropPercent}
                />
              ) : null}
              <Button
                type="submit"
                loading={creatingWatch}
                className="w-full"
                size="lg"
                disabled={!notificationEmailId}
              >
                Deploy watch
              </Button>
              {watchSuccess ? (
                <p className="font-data text-xs text-success text-center" role="status">
                  Watch armed — you will be notified
                </p>
              ) : null}
            </form>
          </div>
        </aside>
      </div>
    </motion.div>
  );
}
