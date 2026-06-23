"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Gear, X } from "@phosphor-icons/react";
import { motion, AnimatePresence } from "motion/react";
import { themes, themeTiers } from "@/lib/themes";
import { useTheme } from "./ThemeProvider";

export function SettingsDrawer() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const panel = (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-[20000]">
          <motion.button
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/75 backdrop-blur-md"
            onClick={() => setOpen(false)}
            aria-label="Close settings"
          />
          <motion.aside
            initial={{ opacity: 0, x: 48 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 48 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="absolute right-0 top-0 h-full w-full max-w-lg holo-panel-strong border-l border-border-bright flex flex-col shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label="Settings"
          >
            <div className="flex h-16 items-center justify-between px-6 border-b border-border shrink-0">
              <div>
                <p className="font-display font-bold text-lg text-ink">Settings</p>
                <p className="font-data text-[12px] uppercase tracking-widest text-muted mt-0.5">
                  Visual systems
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-muted hover:text-ink p-2"
                aria-label="Close"
              >
                <X className="size-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-8">
              {themeTiers.map(({ tier, label }) => (
                <section key={tier}>
                  <h3 className="font-data text-[12px] uppercase tracking-[0.25em] text-muted mb-4">
                    {label}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {themes
                      .filter((t) => t.tier === tier)
                      .map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setTheme(t.id)}
                          className={[
                            "text-left rounded-[var(--radius-lg)] border p-4 transition-all",
                            theme === t.id
                              ? "border-accent bg-accent/10 shadow-[0_0_24px_var(--glow-accent)]"
                              : "border-border hover:border-border-bright hover:bg-surface-raised/50",
                          ].join(" ")}
                        >
                          <div className="flex items-center gap-3 mb-2">
                            <span
                              className="size-10 rounded-full shrink-0 border border-white/10"
                              style={{ background: t.preview }}
                            />
                            <span className="font-display font-semibold text-base text-ink">
                              {t.label}
                            </span>
                          </div>
                          <p className="font-data text-[13px] text-muted leading-snug">
                            {t.description}
                          </p>
                        </button>
                      ))}
                  </div>
                </section>
              ))}

              <section className="rounded-[var(--radius-lg)] border border-border p-4">
                <h3 className="font-data text-[12px] uppercase tracking-[0.25em] text-muted mb-2">
                  Shortcuts
                </h3>
                <ul className="font-data text-sm text-muted space-y-2">
                  <li>
                    <kbd className="text-accent">⌘K</kbd> — Global search
                  </li>
                  <li>
                    <kbd className="text-accent">?</kbd> — Keyboard help
                  </li>
                </ul>
              </section>
            </div>
          </motion.aside>
        </div>
      ) : null}
    </AnimatePresence>
  );

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex size-10 items-center justify-center rounded-[var(--radius-md)] holo-panel text-muted hover:text-accent transition-colors"
        aria-label="Open settings"
      >
        <Gear className="size-5" />
      </button>
      {mounted ? createPortal(panel, document.body) : null}
    </>
  );
}
