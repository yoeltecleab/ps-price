"use client";

import Link from "next/link";
import { UserCircle } from "@phosphor-icons/react";
import { useAuth } from "@/lib/auth";
import { Button } from "./Button";

export function AuthMenu() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="size-9 rounded-full bg-surface/50 animate-pulse" />;
  }

  if (!user) {
    return (
      <Link href="/auth/login">
        <Button variant="secondary" size="sm">
          Sign in
        </Button>
      </Link>
    );
  }

  return (
    <Link
      href={user.is_admin ? "/admin" : "/account"}
      className="flex items-center gap-2 rounded-[var(--radius-md)] border border-border/60 px-3 py-2 hover:border-accent/40 transition-colors"
    >
      <UserCircle className="size-5 text-accent" weight="fill" />
      <span className="hidden md:inline font-data text-xs text-ink max-w-[140px] truncate">
        {user.display_name || user.email}
      </span>
      {user.is_admin ? (
        <span className="hidden lg:inline font-data text-[10px] uppercase tracking-widest text-accent px-1.5 py-0.5 rounded border border-accent/30">
          Admin
        </span>
      ) : null}
    </Link>
  );
}
