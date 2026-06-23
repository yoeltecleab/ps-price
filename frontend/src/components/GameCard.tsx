"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowsClockwise, Trash } from "@phosphor-icons/react";
import type { Game } from "@/lib/types";
import { discountPercent, formatRelativeTime } from "@/lib/format";
import { Badge } from "./Badge";
import { Button } from "./Button";

export function GameCard({
  game,
  onRefresh,
  onDelete,
  refreshing,
  selected,
  onSelect,
}: {
  game: Game;
  onRefresh?: () => void;
  onDelete?: () => void;
  refreshing?: boolean;
  selected?: boolean;
  onSelect?: (id: number, checked: boolean) => void;
}) {
  const discount = discountPercent(
    game.current_price_cents,
    game.original_price_cents,
  );
  const hasError = Boolean(game.last_error);

  return (
    <article
      className={[
        "group flex gap-4 p-4 rounded-[var(--radius-lg)] bg-surface border border-border hover:border-primary/30 transition-colors duration-150 animate-fade-in",
        selected ? "ring-2 ring-accent/40" : "",
      ].join(" ")}
    >
      {onSelect ? (
        <label className="flex items-start pt-1 shrink-0 cursor-pointer">
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => onSelect(game.id, e.target.checked)}
            className="size-4 accent-accent"
            aria-label={`Select ${game.name}`}
          />
        </label>
      ) : null}
      <Link href={`/games/${game.id}`} className="shrink-0">
        <div className="relative size-20 rounded-[var(--radius-md)] overflow-hidden bg-surface-raised">
          {game.image_url ? (
            <Image
              src={game.image_url}
              alt=""
              width={80}
              height={80}
              className="object-cover size-full"
              unoptimized
            />
          ) : (
            <div className="flex size-full items-center justify-center text-muted text-xs">
              No art
            </div>
          )}
        </div>
      </Link>

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Link
              href={`/games/${game.id}`}
              className="text-sm font-semibold text-ink hover:text-accent transition-colors line-clamp-2"
            >
              {game.name}
            </Link>
            <p className="text-xs text-muted mt-1 font-mono truncate">
              {game.product_id}
            </p>
          </div>
          {discount ? (
            <Badge variant="accent">-{discount}%</Badge>
          ) : null}
        </div>

        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-lg font-semibold font-mono tabular-nums text-ink">
            {game.current_price_formatted ?? "—"}
          </span>
          {game.original_price_formatted &&
          game.original_price_cents !== game.current_price_cents ? (
            <span className="text-sm text-muted font-mono line-through">
              {game.original_price_formatted}
            </span>
          ) : null}
        </div>

        <div className="mt-2 flex items-center gap-2 flex-wrap">
          {hasError ? (
            <Badge variant="error">Error</Badge>
          ) : (
            <Badge variant="success">{game.availability}</Badge>
          )}
          <span className="text-xs text-muted">
            Checked {formatRelativeTime(game.last_checked_at)}
          </span>
        </div>

        {onRefresh || onDelete ? (
          <div className="mt-3 flex gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            {onRefresh ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={onRefresh}
                loading={refreshing}
                aria-label={`Refresh ${game.name}`}
              >
                <ArrowsClockwise className="size-3.5" aria-hidden />
                Refresh
              </Button>
            ) : null}
            {onDelete ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={onDelete}
                aria-label={`Remove ${game.name}`}
              >
                <Trash className="size-3.5" aria-hidden />
                Remove
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}
