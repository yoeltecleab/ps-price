"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/components/ThemeProvider";
import { normalizeThemeId } from "@/lib/themes";

/** Persist UI theme to the account and restore server preference on login. */
export function ThemeSync() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    if (!user?.preferred_theme_id) return;
    setTheme(normalizeThemeId(user.preferred_theme_id));
  }, [user?.id, user?.preferred_theme_id, setTheme]);

  useEffect(() => {
    if (!user) return;
    void api("/api/auth/profile", {
      method: "PATCH",
      body: JSON.stringify({ preferred_theme_id: theme }),
    }).catch(() => undefined);
  }, [theme, user?.id]);

  return null;
}
