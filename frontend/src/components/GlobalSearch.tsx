"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { MagnifyingGlass, Command } from "@phosphor-icons/react";
import { motion, AnimatePresence } from "motion/react";
import type { SearchResult } from "@/lib/types";

function parseFetchError(body: string, status: number): string {
  try {
    const data = JSON.parse(body) as { detail?: string | { msg?: string }[] };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg ?? "").filter(Boolean).join(", ");
    }
  } catch {
    /* ignore */
  }
  return body || `Search failed (${status})`;
}

export function GlobalSearch() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, left: 0, width: 0 });
  const [positioned, setPositioned] = useState(false);
  const [mounted, setMounted] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => setMounted(true), []);

  const updatePosition = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const width = Math.max(rect.width, 360);
    const left = Math.min(rect.left, window.innerWidth - width - 16);
    setDropdownPos({
      top: rect.bottom + 8,
      left: Math.max(8, left),
      width,
    });
    setPositioned(true);
  }, []);

  const search = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/search?q=${encodeURIComponent(trimmed)}&limit=48`,
        { signal: controller.signal, cache: "no-store" },
      );
      if (!res.ok) {
        const text = await res.text();
        throw new Error(parseFetchError(text, res.status));
      }
      const data = (await res.json()) as SearchResult[];
      if (!controller.signal.aborted) {
        setResults(data.filter((row) => row.id != null));
        setActiveIndex(data.length ? 0 : -1);
        updatePosition();
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setResults([]);
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [updatePosition]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    setOpen(true);
    debounceRef.current = setTimeout(() => search(query), 220);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, search]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
        inputRef.current?.focus();
      }
      if (e.key === "/" && !typing) {
        e.preventDefault();
        setOpen(true);
        inputRef.current?.focus();
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useLayoutEffect(() => {
    if (!open || !query.trim()) {
      setPositioned(false);
      return;
    }
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, query, updatePosition]);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target)) return;
      const dropdown = document.getElementById("global-search-portal");
      if (dropdown?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const showDropdown = open && query.trim().length > 0 && positioned;

  function openResult(result: SearchResult) {
    if (!result.id) return;
    setOpen(false);
    router.push(`/games/${result.id}`);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" && results.length) {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp" && results.length) {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      const pick = activeIndex >= 0 ? results[activeIndex] : results[0];
      if (pick) {
        e.preventDefault();
        openResult(pick);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function editionTags(item: SearchResult): string[] {
    const tags: string[] = [];
    for (const platform of item.platforms ?? []) {
      if (platform && !tags.includes(platform)) tags.push(platform);
    }
    const name = item.name.toLowerCase();
    if (name.includes("upgrade") || name.includes("dlc")) tags.push("DLC");
    return tags;
  }

  function renderResult(item: SearchResult, index: number) {
    const tags = editionTags(item);
    return (
      <li key={item.id ?? item.product_id} role="option" aria-selected={index === activeIndex}>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => openResult(item)}
          className={[
            "w-full flex items-center gap-4 px-4 py-3.5 text-left transition-colors",
            index === activeIndex ? "bg-primary/15" : "hover:bg-surface-raised/80",
          ].join(" ")}
        >
          <div className="size-12 shrink-0 rounded-[var(--radius-sm)] overflow-hidden bg-surface-raised border border-border">
            {item.image_url ? (
              <Image
                src={item.image_url}
                alt=""
                width={48}
                height={48}
                className="object-cover size-full"
                unoptimized
              />
            ) : (
              <div className="size-full flex items-center justify-center text-muted text-xs">?</div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium text-ink truncate">{item.name}</p>
            {tags.length ? (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className={[
                      "font-data text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-full border",
                      tag === "DLC"
                        ? "border-border text-muted"
                        : "border-primary/40 text-primary",
                    ].join(" ")}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="shrink-0 text-right pl-2">
            <p className="font-display text-lg font-bold tabular-nums text-ink">
              {item.current_price_formatted ?? "—"}
            </p>
            {item.discount_percent ? (
              <p className="font-data text-xs text-accent mt-0.5">−{item.discount_percent}%</p>
            ) : null}
          </div>
          {item.is_tracked ? (
            <span className="shrink-0 text-[13px] font-data uppercase tracking-widest text-accent px-2 py-0.5 rounded-full border border-accent/30">
              Library
            </span>
          ) : null}
        </button>
      </li>
    );
  }

  const dropdown = (
    <AnimatePresence>
      {showDropdown ? (
        <motion.div
          id="global-search-portal"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: "fixed",
            top: dropdownPos.top,
            left: dropdownPos.left,
            width: dropdownPos.width,
            zIndex: 15000,
          }}
          className="rounded-[var(--radius-xl)] holo-panel-strong overflow-hidden shadow-2xl border border-border-bright max-h-[min(70vh,32rem)] overflow-y-auto"
          role="listbox"
        >
          <div className="px-4 py-2.5 border-b border-border/50 font-data text-[12px] uppercase tracking-widest text-muted sticky top-0 bg-surface-raised/95 backdrop-blur-sm flex justify-between">
            <span>{results.length ? `${results.length} catalog matches` : "Search"}</span>
            {loading ? <span className="text-accent animate-pulse">Scanning…</span> : null}
          </div>

          {loading && results.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted animate-pulse text-center">
              Searching local catalog…
            </p>
          ) : error ? (
            <p className="px-5 py-4 text-sm text-error">{error}</p>
          ) : !loading && results.length === 0 ? (
            <p className="px-5 py-4 text-sm text-muted">
              No matches for &ldquo;{query.trim()}&rdquo; in the local catalog yet. If the server
              just deployed, wait for the startup sync to finish.
            </p>
          ) : (
            <ul>{results.map((item, index) => renderResult(item, index))}</ul>
          )}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );

  return (
    <div ref={anchorRef} className="relative w-full">
      <MagnifyingGlass
        className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-muted pointer-events-none"
        aria-hidden
      />
      <input
        ref={inputRef}
        type="text"
        inputMode="search"
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          updatePosition();
        }}
        onKeyDown={handleKeyDown}
        placeholder="Search the catalog…"
        className="h-12 w-full rounded-[var(--radius-md)] holo-panel pl-10 pr-24 text-base text-ink placeholder:text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 font-data"
        aria-label="Search games"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls="global-search-portal"
      />
      <kbd className="hidden sm:flex absolute right-3 top-1/2 -translate-y-1/2 items-center gap-1 px-2 py-0.5 rounded-[var(--radius-sm)] border border-border text-[12px] font-data text-muted pointer-events-none">
        <Command className="size-3.5" />K
      </kbd>
      {mounted ? createPortal(dropdown, document.body) : null}
    </div>
  );
}
