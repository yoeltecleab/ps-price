"use client";

import Image from "next/image";
import Link from "next/link";
import { memo, useCallback } from "react";
import { BookmarkSimple, Bookmark, ArrowUpRight } from "@phosphor-icons/react";
import { motion } from "motion/react";
import type { Game } from "@/lib/types";
import { Button } from "./Button";

export const DealCard = memo(function DealCard({
  game,
  onTrack,
  tracking,
  index = 0,
  selected,
  onSelect,
}: {
  game: Game;
  onTrack?: () => void;
  tracking?: boolean;
  index?: number;
  selected?: boolean;
  onSelect?: (id: number, checked: boolean) => void;
}) {
  const discount = game.discount_percent;

  const handleSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onSelect?.(game.id, e.target.checked);
    },
    [game.id, onSelect],
  );

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.35,
        delay: Math.min(index * 0.03, 0.2),
        ease: [0.16, 1, 0.3, 1],
      }}
      className={[
        "group relative flex flex-col holo-panel overflow-hidden rounded-[var(--radius-lg)]",
        selected ? "ring-2 ring-accent/50" : "",
      ].join(" ")}
    >
      {onSelect ? (
        <label className="absolute top-3 left-3 z-30 flex items-center justify-center size-8 rounded-full holo-panel cursor-pointer">
          <input
            type="checkbox"
            checked={selected}
            onChange={handleSelect}
            className="size-4 accent-accent"
            aria-label={`Select ${game.name}`}
          />
        </label>
      ) : null}

      <Link
        href={`/games/${game.id}`}
        className="relative overflow-hidden bg-surface-raised block aspect-[4/3]"
      >
        {game.image_url ? (
          <Image
            src={game.image_url}
            alt=""
            fill
            className="object-cover transition-transform duration-500 group-hover:scale-105"
            sizes="280px"
            unoptimized
          />
        ) : (
          <div className="flex size-full items-center justify-center text-muted text-xs font-data">
            NO SIGNAL
          </div>
        )}

        <div className="absolute inset-0 bg-gradient-to-t from-bg via-transparent to-transparent opacity-80" />

        {discount ? (
          <div className={`absolute top-3 ${onSelect ? "left-12" : "left-3"} z-20 flex flex-col gap-1`}>
            <span className="inline-flex items-center font-data text-sm font-bold text-white px-2.5 py-1 rounded-[var(--radius-sm)] bg-primary shadow-[0_0_20px_var(--glow)]">
              −{discount}%
            </span>
            {discount >= 70 ? (
              <span className="font-data text-[13px] uppercase tracking-widest text-white px-2 py-0.5 rounded bg-error/90">
                Steal
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="absolute top-3 right-3 z-20 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="flex size-8 items-center justify-center rounded-full holo-panel text-accent">
            <ArrowUpRight className="size-4" weight="bold" />
          </span>
        </div>
      </Link>

      <div className="flex flex-col gap-2 p-4">
        <Link
          href={`/games/${game.id}`}
          className="font-display font-semibold text-sm text-ink leading-snug line-clamp-2 hover:text-accent transition-colors"
        >
          {game.name}
        </Link>

        {game.description_short ? (
          <p className="text-xs text-muted line-clamp-2 leading-relaxed">
            {game.description_short}
          </p>
        ) : null}

        <div className="flex items-baseline gap-2 mt-auto pt-1">
          <span className="font-data font-bold tabular-nums text-ink text-lg">
            {game.current_price_formatted ?? "—"}
          </span>
          {game.original_price_formatted &&
          game.original_price_cents !== game.current_price_cents ? (
            <span className="text-sm text-muted font-data line-through opacity-60">
              {game.original_price_formatted}
            </span>
          ) : null}
        </div>

        {onTrack ? (
          <Button
            variant={game.is_tracked ? "secondary" : "primary"}
            size="sm"
            className="w-full mt-2"
            onClick={onTrack}
            loading={tracking}
            disabled={game.is_tracked}
          >
            {game.is_tracked ? (
              <>
                <Bookmark weight="fill" className="size-4" aria-hidden />
                In library
              </>
            ) : (
              <>
                <BookmarkSimple className="size-4" aria-hidden />
                Add to library
              </>
            )}
          </Button>
        ) : null}
      </div>
    </motion.article>
  );
});
