"use client";

import { themes } from "@/lib/themes";
import { useTheme } from "./ThemeProvider";

export function ThemePicker({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <div className={compact ? "flex gap-2" : "space-y-2"}>
      {!compact ? (
        <p className="text-[12px] font-data uppercase tracking-[0.2em] text-muted">
          Visual mode
        </p>
      ) : null}
      <div className="flex gap-2">
        {themes.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTheme(t.id)}
            title={`${t.label} — ${t.description}`}
            aria-label={`${t.label} theme`}
            aria-pressed={theme === t.id}
            className={[
              "relative rounded-full transition-all duration-300",
              compact ? "size-7" : "size-9",
              theme === t.id
                ? "ring-2 ring-accent ring-offset-2 ring-offset-bg scale-110"
                : "opacity-60 hover:opacity-100 hover:scale-105",
            ].join(" ")}
            style={{
              background: t.preview,
              boxShadow:
                theme === t.id
                  ? `0 0 20px ${t.preview.replace(")", " / 0.6)")}`
                  : undefined,
            }}
          />
        ))}
      </div>
    </div>
  );
}
