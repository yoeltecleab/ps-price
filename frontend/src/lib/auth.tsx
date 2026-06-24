"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { safeRedirectPath } from "@/lib/safeRedirect";
import type { AuthUser, MeResponse, NotificationEmail, Passkey } from "@/lib/types";

type AuthState = {
  user: AuthUser | null;
  notificationEmails: NotificationEmail[];
  passkeys: Passkey[];
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  requireVerified: (next?: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [notificationEmails, setNotificationEmails] = useState<NotificationEmail[]>([]);
  const [passkeys, setPasskeys] = useState<Passkey[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api<MeResponse>("/api/auth/me");
      setUser(data.user);
      setNotificationEmails(data.notification_emails);
      setPasskeys(data.passkeys);
    } catch {
      setUser(null);
      setNotificationEmails([]);
      setPasskeys([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signOut = useCallback(async () => {
    await api("/api/auth/logout", { method: "POST" });
    setUser(null);
    setNotificationEmails([]);
    setPasskeys([]);
    router.push("/");
  }, [router]);

  const requireVerified = useCallback(
    (next?: string) => {
      if (!user) {
        router.push(`/auth/login?next=${encodeURIComponent(safeRedirectPath(next, "/"))}`);
        return false;
      }
      if (!user.email_verified) {
        router.push(`/auth/verify?next=${encodeURIComponent(safeRedirectPath(next, "/"))}`);
        return false;
      }
      return true;
    },
    [router, user],
  );

  const value = useMemo(
    () => ({ user, notificationEmails, passkeys, loading, refresh, signOut, requireVerified }),
    [user, notificationEmails, passkeys, loading, refresh, signOut, requireVerified],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function useVerifiedEmails() {
  const { notificationEmails } = useAuth();
  return notificationEmails.filter((e) => e.verified);
}
