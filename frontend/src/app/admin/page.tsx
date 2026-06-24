"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowsClockwise,
  Bell,
  Database,
  Envelope,
  Gauge,
  Key,
  Medal,
  Pulse,
  Shield,
  Trash,
  Users,
  Warning,
  Books,
  GameController,
  Desktop,
} from "@phosphor-icons/react";
import { motion } from "motion/react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { badgeStats, computeAdminBadges } from "@/lib/adminBadges";
import type {
  AdminGameRow,
  AdminLibraryRow,
  AdminNotificationEmailRow,
  AdminNotificationRow,
  AdminOverview,
  AdminPasskeyRow,
  AdminSessionRow,
  AdminUserRow,
  AdminWatchRow,
  Paginated,
} from "@/lib/adminTypes";
import { formatBytes as fmtBytes } from "@/lib/adminTypes";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Badge } from "@/components/Badge";
import { Skeleton } from "@/components/Skeleton";
import { AdminBadgeWall } from "@/components/admin/AdminBadgeWall";

type Tab =
  | "badges"
  | "overview"
  | "activity"
  | "users"
  | "games"
  | "library"
  | "watches"
  | "emails"
  | "security"
  | "catalog"
  | "system";

const tabs: { id: Tab; label: string; icon: typeof Gauge }[] = [
  { id: "badges", label: "Badges", icon: Medal },
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "activity", label: "Activity", icon: Pulse },
  { id: "users", label: "Users", icon: Users },
  { id: "games", label: "Games", icon: GameController },
  { id: "library", label: "Library", icon: Books },
  { id: "watches", label: "Watches", icon: Bell },
  { id: "emails", label: "Email log", icon: Envelope },
  { id: "security", label: "Security", icon: Key },
  { id: "catalog", label: "Catalog", icon: Database },
  { id: "system", label: "System", icon: Shield },
];

function PaginationBar({
  total,
  limit,
  offset,
  onPage,
}: {
  total: number;
  limit: number;
  offset: number;
  onPage: (next: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between px-4 py-3 font-data text-xs text-muted border-t border-border/40">
      <span>
        Page {page} of {pages} · {total} total
      </span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={offset <= 0} onClick={() => onPage(Math.max(0, offset - limit))}>
          Previous
        </Button>
        <Button size="sm" variant="secondary" disabled={offset + limit >= total} onClick={() => onPage(offset + limit)}>
          Next
        </Button>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: boolean }) {
  return (
    <div className="holo-panel rounded-[var(--radius-lg)] p-5 space-y-2">
      <p className="font-data text-[11px] uppercase tracking-[0.2em] text-muted">{label}</p>
      <p className={["font-display text-3xl font-bold tabular-nums", accent ? "text-glow-accent text-accent" : "text-ink"].join(" ")}>
        {value}
      </p>
      {sub ? <p className="font-data text-xs text-muted">{sub}</p> : null}
    </div>
  );
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("badges");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<Paginated<AdminUserRow> | null>(null);
  const [watches, setWatches] = useState<Paginated<AdminWatchRow> | null>(null);
  const [emails, setEmails] = useState<Paginated<AdminNotificationRow> | null>(null);
  const [games, setGames] = useState<Paginated<AdminGameRow> | null>(null);
  const [library, setLibrary] = useState<Paginated<AdminLibraryRow> | null>(null);
  const [sessions, setSessions] = useState<Paginated<AdminSessionRow> | null>(null);
  const [passkeys, setPasskeys] = useState<Paginated<AdminPasskeyRow> | null>(null);
  const [altEmails, setAltEmails] = useState<Paginated<AdminNotificationEmailRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [userQuery, setUserQuery] = useState("");
  const [userOffset, setUserOffset] = useState(0);
  const [watchQuery, setWatchQuery] = useState("");
  const [watchEnabledOnly, setWatchEnabledOnly] = useState(false);
  const [watchOffset, setWatchOffset] = useState(0);
  const [emailStatus, setEmailStatus] = useState("");
  const [emailOffset, setEmailOffset] = useState(0);
  const [expandedEmailId, setExpandedEmailId] = useState<number | null>(null);
  const [gameQuery, setGameQuery] = useState("");
  const [gameOnSaleOnly, setGameOnSaleOnly] = useState(false);
  const [gameOffset, setGameOffset] = useState(0);
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryOffset, setLibraryOffset] = useState(0);
  const [sessionQuery, setSessionQuery] = useState("");
  const [sessionOffset, setSessionOffset] = useState(0);
  const [passkeyQuery, setPasskeyQuery] = useState("");
  const [passkeyOffset, setPasskeyOffset] = useState(0);
  const [altEmailQuery, setAltEmailQuery] = useState("");
  const [altEmailOffset, setAltEmailOffset] = useState(0);
  const [securitySection, setSecuritySection] = useState<"sessions" | "passkeys" | "addresses">("sessions");

  const badgeCount = useMemo(() => badgeStats(computeAdminBadges(overview)).earned, [overview]);

  const loadOverview = useCallback(async () => {
    setOverview(await api<AdminOverview>("/api/admin/overview"));
  }, []);

  const loadUsers = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(userOffset) });
    if (userQuery.trim()) params.set("q", userQuery.trim());
    setUsers(await api(`/api/admin/users?${params}`));
  }, [userQuery, userOffset]);

  const loadWatches = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(watchOffset) });
    if (watchQuery.trim()) params.set("q", watchQuery.trim());
    if (watchEnabledOnly) params.set("enabled_only", "true");
    setWatches(await api(`/api/admin/watches?${params}`));
  }, [watchQuery, watchEnabledOnly, watchOffset]);

  const loadEmails = useCallback(async () => {
    const params = new URLSearchParams({ limit: "100", offset: String(emailOffset) });
    if (emailStatus) params.set("status", emailStatus);
    setEmails(await api(`/api/admin/notifications?${params}`));
  }, [emailStatus, emailOffset]);

  const loadGames = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(gameOffset) });
    if (gameQuery.trim()) params.set("q", gameQuery.trim());
    if (gameOnSaleOnly) params.set("on_sale_only", "true");
    setGames(await api(`/api/admin/games?${params}`));
  }, [gameQuery, gameOnSaleOnly, gameOffset]);

  const loadLibrary = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(libraryOffset) });
    if (libraryQuery.trim()) params.set("q", libraryQuery.trim());
    setLibrary(await api(`/api/admin/library?${params}`));
  }, [libraryQuery, libraryOffset]);

  const loadSessions = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(sessionOffset) });
    if (sessionQuery.trim()) params.set("q", sessionQuery.trim());
    setSessions(await api(`/api/admin/sessions?${params}`));
  }, [sessionQuery, sessionOffset]);

  const loadPasskeys = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(passkeyOffset) });
    if (passkeyQuery.trim()) params.set("q", passkeyQuery.trim());
    setPasskeys(await api(`/api/admin/passkeys?${params}`));
  }, [passkeyQuery, passkeyOffset]);

  const loadAltEmails = useCallback(async () => {
    const params = new URLSearchParams({ limit: "50", offset: String(altEmailOffset) });
    if (altEmailQuery.trim()) params.set("q", altEmailQuery.trim());
    setAltEmails(await api(`/api/admin/notification-emails?${params}`));
  }, [altEmailQuery, altEmailOffset]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadOverview();
      if (tab === "users") await loadUsers();
      if (tab === "watches") await loadWatches();
      if (tab === "emails") await loadEmails();
      if (tab === "games") await loadGames();
      if (tab === "library") await loadLibrary();
      if (tab === "security") {
        if (securitySection === "sessions") await loadSessions();
        if (securitySection === "passkeys") await loadPasskeys();
        if (securitySection === "addresses") await loadAltEmails();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, [tab, securitySection, loadOverview, loadUsers, loadWatches, loadEmails, loadGames, loadLibrary, loadSessions, loadPasskeys, loadAltEmails]);

  useEffect(() => {
    if (authLoading) return;
    if (!user?.is_admin) {
      router.replace("/");
      return;
    }
    void refresh();
  }, [authLoading, user, router, refresh, tab, securitySection, userOffset, watchOffset, emailOffset, gameOffset, libraryOffset, sessionOffset, passkeyOffset, altEmailOffset]);

  async function runAction(fn: () => Promise<void>, success: string) {
    setActionLoading(true);
    setNotice(null);
    setError(null);
    try {
      await fn();
      setNotice(success);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionLoading(false);
    }
  }

  if (authLoading || !user?.is_admin) {
    return (
      <div className="space-y-4 py-12">
        <Skeleton className="h-12 w-64" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    );
  }

  const notifTotal = Object.values(overview?.notifications ?? {}).reduce((a, b) => a + b, 0);
  const insights = overview?.insights;

  return (
    <div className="space-y-8 pb-16">
      <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
        <div>
          <p className="font-data text-xs uppercase tracking-[0.35em] text-accent mb-2">Command center</p>
          <h1 className="font-display text-4xl md:text-5xl font-extrabold text-ink tracking-tight">Admin dashboard</h1>
          <p className="mt-2 text-sm text-muted max-w-xl">
            {badgeCount.toLocaleString()} badges earned · users, catalog, security, alerts, and ops — full marshal kit.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => refresh()} loading={loading}>
            <ArrowsClockwise className="size-4" />
            Refresh
          </Button>
          <Button loading={actionLoading} onClick={() => runAction(() => api("/api/admin/sync", { method: "POST" }), "Catalog sync started.")}>
            Force catalog sync
          </Button>
        </div>
      </header>

      {error ? (
        <div className="rounded-[var(--radius-md)] border border-error/40 bg-error/10 px-4 py-3 text-sm text-error flex items-center gap-2">
          <Warning className="size-4 shrink-0" />
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-[var(--radius-md)] border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent">{notice}</div>
      ) : null}

      <nav className="flex flex-wrap gap-2 border-b border-border/60 pb-1">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={[
              "flex items-center gap-2 px-3 py-2.5 rounded-t-[var(--radius-md)] font-data text-[10px] sm:text-xs uppercase tracking-wider transition-colors",
              tab === id ? "text-accent border-b-2 border-accent bg-surface/40" : "text-muted hover:text-ink",
            ].join(" ")}
          >
            <Icon className="size-4" />
            {label}
            {id === "badges" ? (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-accent/20 text-accent">{badgeCount}</span>
            ) : null}
          </button>
        ))}
      </nav>

      {tab === "badges" ? (
        <AdminBadgeWall overview={overview} adminName={user.display_name || user.email} />
      ) : null}

      {tab === "overview" && overview ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <StatCard label="Badges" value={badgeCount.toLocaleString()} sub="On your uniform" accent />
            <StatCard label="Users" value={overview.users.total} sub={`${overview.users.verified} verified`} accent />
            <StatCard label="Catalog" value={overview.catalog.total_games.toLocaleString()} sub={`${overview.catalog.on_sale.toLocaleString()} on sale`} />
            <StatCard label="Watches" value={overview.watches.enabled} sub={`${overview.watches.total} total`} accent />
            <StatCard label="Emails" value={notifTotal} sub={`${overview.notifications.sent ?? 0} sent`} />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <section className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-4">
              <h2 className="font-display text-lg font-bold text-ink">Top watched games</h2>
              <ul className="space-y-2 text-sm">
                {(insights?.top_watched_games ?? []).map((g) => (
                  <li key={g.id} className="flex justify-between gap-2 border-b border-border/30 pb-2">
                    <Link href={`/games/${g.id}`} className="text-ink hover:text-accent truncate">{g.name}</Link>
                    <span className="font-data text-xs text-muted shrink-0">{g.watch_count} watches</span>
                  </li>
                ))}
                {!insights?.top_watched_games.length ? <li className="text-muted">No watches yet</li> : null}
              </ul>
            </section>
            <section className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-4">
              <h2 className="font-display text-lg font-bold text-ink">Email delivery</h2>
              {["sent", "failed", "skipped", "pending"].map((status) => {
                const count = overview.notifications[status] ?? 0;
                const pct = notifTotal ? Math.round((count / notifTotal) * 100) : 0;
                return (
                  <div key={status}>
                    <div className="flex justify-between font-data text-xs uppercase tracking-wider text-muted mb-1">
                      <span>{status}</span>
                      <span>{count} ({pct}%)</span>
                    </div>
                    <div className="h-2 rounded-full bg-surface overflow-hidden">
                      <div className={["h-full rounded-full", status === "sent" ? "bg-accent" : status === "failed" ? "bg-error" : "bg-muted/60"].join(" ")} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </section>
          </div>
        </motion.div>
      ) : null}

      {tab === "activity" && insights ? (
        <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {[
            { title: "New users", items: insights.recent_users, render: (u: (typeof insights.recent_users)[0]) => (
              <span>{u.email} · {formatRelativeTime(u.created_at)}</span>
            )},
            { title: "New watches", items: insights.recent_watches, render: (w: (typeof insights.recent_watches)[0]) => (
              <span>{w.game_name} · {w.user_email ?? "guest"}</span>
            )},
            { title: "Recent emails", items: insights.recent_emails, render: (e: (typeof insights.recent_emails)[0]) => (
              <span className="flex items-center gap-2"><Badge variant={e.status === "sent" ? "success" : e.status === "failed" ? "error" : "warning"}>{e.status}</Badge>{e.subject}</span>
            )},
          ].map(({ title, items, render }) => (
            <div key={title} className="holo-panel rounded-[var(--radius-xl)] p-6 space-y-3">
              <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
              <ul className="space-y-2 text-sm text-muted">
                {items.map((item) => (
                  <li key={"id" in item ? item.id : (item as { email: string }).email} className="border-b border-border/30 pb-2">{render(item as never)}</li>
                ))}
                {!items.length ? <li>Nothing yet</li> : null}
              </ul>
            </div>
          ))}
          <div className="holo-panel rounded-[var(--radius-xl)] p-6 xl:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Avg discount" value={`${insights.avg_discount_percent}%`} />
            <StatCard label="Price history" value={insights.price_history_rows.toLocaleString()} />
            <StatCard label="Unverified" value={insights.unverified_users} accent={insights.unverified_users > 0} />
            <StatCard label="Alt emails" value={insights.notification_emails} />
          </div>
        </section>
      ) : null}

      {tab === "users" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px] max-w-md">
              <Input label="Search users" value={userQuery} onChange={(e) => setUserQuery(e.target.value)} placeholder="Email or display name" />
            </div>
            <Button variant="secondary" onClick={() => { setUserOffset(0); void loadUsers(); }}>Search</Button>
          </div>
          <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead>
                <tr className="border-b border-border/60 font-data text-[11px] uppercase tracking-widest text-muted">
                  <th className="text-left px-4 py-3">User</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="text-right px-4 py-3">Lib</th>
                  <th className="text-right px-4 py-3">Watch</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(users?.items ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-border/30 hover:bg-surface/40">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">{row.email}</p>
                      {row.display_name ? <p className="text-xs text-muted">{row.display_name}</p> : null}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {row.email_verified ? <Badge variant="success">Verified</Badge> : <Badge variant="warning">Unverified</Badge>}
                        {row.has_password ? <Badge>Password</Badge> : null}
                        {row.passkey_count > 0 ? <Badge>{row.passkey_count} keys</Badge> : null}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{row.library_count}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{row.watch_count}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 justify-end">
                        {!row.email_verified ? (
                          <>
                            <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => runAction(() => api(`/api/admin/users/${row.id}/verify`, { method: "POST" }), "User verified.")}>Verify</Button>
                            <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => runAction(() => api(`/api/admin/users/${row.id}/resend-verification`, { method: "POST" }), "Verification sent.")}>Resend</Button>
                          </>
                        ) : null}
                        <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => runAction(() => api(`/api/admin/users/${row.id}/revoke-sessions`, { method: "POST" }), "Sessions revoked.")}>Revoke</Button>
                        {row.id !== user.id ? (
                          <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => { if (window.confirm(`Delete ${row.email}?`)) void runAction(() => api(`/api/admin/users/${row.id}`, { method: "DELETE" }), "User deleted."); }}>
                            <Trash className="size-3.5" />
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users ? <PaginationBar total={users.total} limit={users.limit} offset={users.offset} onPage={setUserOffset} /> : null}
          </div>
        </section>
      ) : null}

      {tab === "games" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px] max-w-md">
              <Input label="Search catalog" value={gameQuery} onChange={(e) => setGameQuery(e.target.value)} placeholder="Game name" />
            </div>
            <label className="flex items-center gap-2 font-data text-xs text-muted pb-2">
              <input type="checkbox" checked={gameOnSaleOnly} onChange={(e) => setGameOnSaleOnly(e.target.checked)} />
              On sale only
            </label>
            <Button variant="secondary" onClick={() => { setGameOffset(0); void loadGames(); }}>Search</Button>
          </div>
          <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
            <table className="w-full text-sm min-w-[800px]">
              <thead>
                <tr className="border-b border-border/60 font-data text-[11px] uppercase tracking-widest text-muted">
                  <th className="text-left px-4 py-3">Game</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="text-right px-4 py-3">Discount</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {(games?.items ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-border/30 hover:bg-surface/40">
                    <td className="px-4 py-3">
                      <Link href={`/games/${row.id}`} className="font-medium text-ink hover:text-accent">{row.name}</Link>
                    </td>
                    <td className="px-4 py-3 text-right">{row.current_price_formatted ?? "—"}</td>
                    <td className="px-4 py-3 text-right">{row.discount_percent ? `${row.discount_percent}%` : "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-1 justify-end">
                        <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => runAction(() => api(`/api/admin/games/${row.id}/refresh`, { method: "POST" }), "Game refreshed.")}>Refresh</Button>
                        <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => { if (window.confirm(`Delete ${row.name}?`)) void runAction(() => api(`/api/admin/games/${row.id}`, { method: "DELETE" }), "Game deleted."); }}>
                          <Trash className="size-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {games ? <PaginationBar total={games.total} limit={games.limit} offset={games.offset} onPage={setGameOffset} /> : null}
          </div>
        </section>
      ) : null}

      {tab === "library" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px] max-w-md">
              <Input label="Search library" value={libraryQuery} onChange={(e) => setLibraryQuery(e.target.value)} placeholder="Game or user email" />
            </div>
            <Button variant="secondary" onClick={() => { setLibraryOffset(0); void loadLibrary(); }}>Search</Button>
          </div>
          <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="border-b border-border/60 font-data text-[11px] uppercase tracking-widest text-muted">
                  <th className="text-left px-4 py-3">User</th>
                  <th className="text-left px-4 py-3">Game</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="text-right px-4 py-3">Added</th>
                </tr>
              </thead>
              <tbody>
                {(library?.items ?? []).map((row) => (
                  <tr key={`${row.user_id}-${row.game_id}`} className="border-b border-border/30">
                    <td className="px-4 py-3 text-muted">{row.user_email}</td>
                    <td className="px-4 py-3"><Link href={`/games/${row.game_id}`} className="text-ink hover:text-accent">{row.game_name}</Link></td>
                    <td className="px-4 py-3 text-right">{row.current_price_formatted ?? "—"}</td>
                    <td className="px-4 py-3 text-right text-xs text-muted">{formatDateTime(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {library ? <PaginationBar total={library.total} limit={library.limit} offset={library.offset} onPage={setLibraryOffset} /> : null}
          </div>
        </section>
      ) : null}

      {tab === "watches" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px] max-w-md">
              <Input label="Search watches" value={watchQuery} onChange={(e) => setWatchQuery(e.target.value)} placeholder="Game, email, user" />
            </div>
            <label className="flex items-center gap-2 font-data text-xs text-muted pb-2">
              <input type="checkbox" checked={watchEnabledOnly} onChange={(e) => setWatchEnabledOnly(e.target.checked)} />
              Enabled only
            </label>
            <Button variant="secondary" onClick={() => { setWatchOffset(0); void loadWatches(); }}>Search</Button>
          </div>
          <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="border-b border-border/60 font-data text-[11px] uppercase tracking-widest text-muted">
                  <th className="text-left px-4 py-3">Game</th>
                  <th className="text-left px-4 py-3">Alert email</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {(watches?.items ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-border/30 hover:bg-surface/40">
                    <td className="px-4 py-3 font-medium text-ink max-w-[200px] truncate">{row.game_name}</td>
                    <td className="px-4 py-3 text-muted">{row.email}</td>
                    <td className="px-4 py-3 text-right">{row.current_price_formatted ?? "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="secondary" loading={actionLoading} onClick={() => { if (window.confirm("Delete watch?")) void runAction(() => api(`/api/admin/watches/${row.id}`, { method: "DELETE" }), "Watch deleted."); }}>
                        <Trash className="size-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {watches ? <PaginationBar total={watches.total} limit={watches.limit} offset={watches.offset} onPage={setWatchOffset} /> : null}
          </div>
        </section>
      ) : null}

      {tab === "emails" ? (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <select value={emailStatus} onChange={(e) => setEmailStatus(e.target.value)} className="h-10 rounded-[var(--radius-md)] holo-panel px-3 font-data text-sm">
              <option value="">All statuses</option>
              <option value="sent">Sent</option>
              <option value="failed">Failed</option>
              <option value="skipped">Skipped</option>
            </select>
            <Button variant="secondary" onClick={() => { setEmailOffset(0); void loadEmails(); }}>Apply</Button>
            <Button variant="secondary" loading={actionLoading} onClick={() => { if (window.confirm("Purge all failed email log entries?")) void runAction(() => api("/api/admin/notifications/purge?status=failed", { method: "POST" }), "Failed logs purged."); }}>
              Purge failed
            </Button>
          </div>
          <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
            <table className="w-full text-sm min-w-[800px]">
              <tbody>
                {(emails?.items ?? []).map((row) => (
                  <Fragment key={row.id}>
                    <tr className="border-b border-border/30 hover:bg-surface/40 cursor-pointer" onClick={() => setExpandedEmailId((id) => (id === row.id ? null : row.id))}>
                      <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">{formatDateTime(row.created_at)}</td>
                      <td className="px-4 py-3"><Badge variant={row.status === "sent" ? "success" : row.status === "failed" ? "error" : "warning"}>{row.status}</Badge></td>
                      <td className="px-4 py-3">{row.email}</td>
                      <td className="px-4 py-3 text-muted truncate max-w-[240px]">{row.subject}</td>
                      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button size="sm" variant="secondary" onClick={() => runAction(() => api(`/api/admin/notifications/${row.id}`, { method: "DELETE" }), "Removed.")}>
                          <Trash className="size-3.5" />
                        </Button>
                      </td>
                    </tr>
                    {expandedEmailId === row.id && (row.error || row.reason) ? (
                      <tr className="bg-surface/30"><td colSpan={5} className="px-4 py-2 text-xs text-muted">{row.reason} {row.error}</td></tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {emails ? <PaginationBar total={emails.total} limit={emails.limit} offset={emails.offset} onPage={setEmailOffset} /> : null}
          </div>
        </section>
      ) : null}

      {tab === "security" ? (
        <section className="space-y-4">
          <div className="flex gap-2">
            {(["sessions", "passkeys", "addresses"] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSecuritySection(s)} className={["px-4 py-2 rounded-[var(--radius-md)] font-data text-xs uppercase tracking-wider border", securitySection === s ? "border-accent text-accent bg-accent/10" : "border-border/50 text-muted"].join(" ")}>
                {s}
              </button>
            ))}
          </div>
          {securitySection === "sessions" ? (
            <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
              <table className="w-full text-sm min-w-[800px]">
                <thead><tr className="border-b border-border/60 font-data text-[11px] uppercase text-muted"><th className="px-4 py-3 text-left">User</th><th className="px-4 py-3 text-left">Agent</th><th className="px-4 py-3 text-left">IP</th><th className="px-4 py-3 text-right">Expires</th></tr></thead>
                <tbody>
                  {(sessions?.items ?? []).map((row) => (
                    <tr key={row.id} className="border-b border-border/30">
                      <td className="px-4 py-3">{row.user_email}</td>
                      <td className="px-4 py-3 text-xs text-muted max-w-[200px] truncate">{row.user_agent ?? "—"}</td>
                      <td className="px-4 py-3 text-muted">{row.ip_address ?? "—"}</td>
                      <td className="px-4 py-3 text-right text-xs">{formatDateTime(row.expires_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sessions ? <PaginationBar total={sessions.total} limit={sessions.limit} offset={sessions.offset} onPage={setSessionOffset} /> : null}
            </div>
          ) : null}
          {securitySection === "passkeys" ? (
            <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
              <table className="w-full text-sm min-w-[700px]">
                <thead><tr className="border-b border-border/60 font-data text-[11px] uppercase text-muted"><th className="px-4 py-3 text-left">User</th><th className="px-4 py-3 text-left">Name</th><th className="px-4 py-3 text-right">Uses</th><th className="px-4 py-3" /></tr></thead>
                <tbody>
                  {(passkeys?.items ?? []).map((row) => (
                    <tr key={row.id} className="border-b border-border/30">
                      <td className="px-4 py-3">{row.user_email}</td>
                      <td className="px-4 py-3 text-muted">{row.friendly_name ?? "Passkey"}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{row.sign_count}</td>
                      <td className="px-4 py-3 text-right">
                        <Button size="sm" variant="secondary" onClick={() => runAction(() => api(`/api/admin/passkeys/${row.id}`, { method: "DELETE" }), "Passkey revoked.")}>
                          <Trash className="size-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {passkeys ? <PaginationBar total={passkeys.total} limit={passkeys.limit} offset={passkeys.offset} onPage={setPasskeyOffset} /> : null}
            </div>
          ) : null}
          {securitySection === "addresses" ? (
            <div className="holo-panel rounded-[var(--radius-xl)] overflow-x-auto">
              <table className="w-full text-sm min-w-[700px]">
                <thead><tr className="border-b border-border/60 font-data text-[11px] uppercase text-muted"><th className="px-4 py-3 text-left">Owner</th><th className="px-4 py-3 text-left">Address</th><th className="px-4 py-3">Status</th></tr></thead>
                <tbody>
                  {(altEmails?.items ?? []).map((row) => (
                    <tr key={row.id} className="border-b border-border/30">
                      <td className="px-4 py-3 text-muted">{row.user_email}</td>
                      <td className="px-4 py-3">{row.email}{row.is_primary ? " (primary)" : ""}</td>
                      <td className="px-4 py-3">{row.verified ? <Badge variant="success">Verified</Badge> : <Badge variant="warning">Pending</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {altEmails ? <PaginationBar total={altEmails.total} limit={altEmails.limit} offset={altEmails.offset} onPage={setAltEmailOffset} /> : null}
            </div>
          ) : null}
        </section>
      ) : null}

      {tab === "catalog" && overview ? (
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">Sync controls</h2>
            <p className="text-sm text-muted">Last sync: {formatDateTime(overview.sync.last_sync)}</p>
            <div className="flex flex-col gap-2">
              <Button loading={actionLoading} onClick={() => runAction(() => api("/api/admin/sync?background=true", { method: "POST" }), "Background sync queued.")}>Background sync</Button>
              <Button variant="secondary" loading={actionLoading} onClick={() => runAction(() => api("/api/admin/refresh-due", { method: "POST" }), "Due games refreshed.")}>Refresh due library</Button>
            </div>
          </div>
          <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6">
            <h2 className="font-display text-lg font-bold mb-4">Catalog stats</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-muted">Total games</dt><dd>{overview.catalog.total_games.toLocaleString()}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">On sale</dt><dd>{overview.catalog.on_sale.toLocaleString()}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Library entries</dt><dd>{overview.catalog.library_entries}</dd></div>
            </dl>
          </div>
        </section>
      ) : null}

      {tab === "system" && overview ? (
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-3">
            <h2 className="font-display text-lg font-bold flex items-center gap-2"><Desktop className="size-5 text-accent" /> Runtime</h2>
            {[
              ["Scheduler", overview.system.scheduler_enabled ? "Enabled" : "Disabled"],
              ["Production", overview.system.production_mode ? "On" : "Off"],
              ["SMTP", overview.system.smtp_configured ? "Configured" : "Missing"],
              ["Locale", overview.system.store_locale],
              ["DB size", fmtBytes(overview.system.database_bytes)],
              ["Rate buckets", String(overview.system.rate_limit_buckets)],
              ["Check interval", `${overview.system.check_interval_minutes}m`],
              ["Feed sync", `${overview.system.feed_sync_interval_minutes}m`],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm border-b border-border/30 pb-2"><span className="text-muted">{k}</span><span>{v}</span></div>
            ))}
          </div>
          <div className="holo-panel-strong rounded-[var(--radius-xl)] p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">Health</h2>
            <Button
              variant="secondary"
              onClick={() =>
                api<{ catalog_total?: number; syncing?: boolean }>("/api/sync-status").then(
                  (h) => setNotice(`Catalog total: ${h.catalog_total ?? "n/a"}, syncing: ${h.syncing ? "yes" : "no"}`),
                )
              }
            >
              Ping sync status
            </Button>
            <p className="text-xs text-muted font-data break-all">{overview.system.database_path}</p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
