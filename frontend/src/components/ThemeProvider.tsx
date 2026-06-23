"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  defaultTheme,
  normalizeThemeId,
  type ThemeId,
  themes,
} from "@/lib/themes";

interface ThemeContextValue {
  theme: ThemeId;
  setTheme: (id: ThemeId) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(defaultTheme);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("ps-price-theme");
    setThemeState(normalizeThemeId(stored));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const def = themes.find((t) => t.id === theme);
    if (!def) return;
    const root = document.documentElement;
    Object.entries(def.vars).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
    root.dataset.theme = theme;
    root.style.colorScheme =
      def.tier === "light" ? "light" : def.tier === "mid" ? "light dark" : "dark";
    localStorage.setItem("ps-price-theme", theme);
  }, [theme, ready]);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
