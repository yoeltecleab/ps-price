"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "@phosphor-icons/react";
import { motion, AnimatePresence } from "motion/react";

const shortcuts = [
  { keys: "⌘ K", desc: "Focus global search" },
  { keys: "/", desc: "Focus search from anywhere" },
  { keys: "↑ ↓ Enter", desc: "Navigate and open search results" },
  { keys: "Esc", desc: "Close search or settings" },
  { keys: "?", desc: "Show this help" },
];

export function KeyboardHelp() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if (e.key === "?" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const modal = (
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-[25000] flex items-center justify-center p-4">
          <motion.button
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/75 backdrop-blur-md"
            onClick={() => setOpen(false)}
            aria-label="Close"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            className="relative w-full max-w-md holo-panel-strong rounded-[var(--radius-xl)] p-6 border border-border-bright"
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-display font-bold text-lg text-ink">Keyboard shortcuts</h2>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close">
                <X className="size-5 text-muted" />
              </button>
            </div>
            <ul className="space-y-3">
              {shortcuts.map((s) => (
                <li key={s.keys} className="flex items-center justify-between gap-4">
                  <span className="font-data text-sm text-muted">{s.desc}</span>
                  <kbd className="font-data text-sm text-accent px-2 py-1 rounded border border-border">
                    {s.keys}
                  </kbd>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  );

  return mounted ? createPortal(modal, document.body) : null;
}
