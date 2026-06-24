import type { AdminOverview } from "./adminTypes";

export type BadgeTier = "bronze" | "silver" | "gold" | "platinum" | "neon";

export interface AdminBadge {
  id: string;
  title: string;
  description: string;
  category: string;
  tier: BadgeTier;
  emoji: string;
  earned: boolean;
}

const tierColors: Record<BadgeTier, string> = {
  bronze: "border-amber-700/50 bg-amber-950/40 text-amber-200",
  silver: "border-slate-400/50 bg-slate-800/40 text-slate-200",
  gold: "border-yellow-500/50 bg-yellow-950/30 text-yellow-200",
  platinum: "border-cyan-300/50 bg-cyan-950/30 text-cyan-100",
  neon: "border-accent/60 bg-accent/10 text-accent shadow-[0_0_12px_rgba(var(--accent-rgb),0.25)]",
};

export function badgeClass(tier: BadgeTier, earned: boolean): string {
  if (!earned) return "border-border/40 bg-surface/20 text-muted/50 opacity-40 grayscale";
  return tierColors[tier];
}

export function computeAdminBadges(overview: AdminOverview | null): AdminBadge[] {
  const o = overview;
  const u = o?.users;
  const c = o?.catalog;
  const w = o?.watches;
  const n = o?.notifications ?? {};
  const i = o?.insights;
  const s = o?.system;
  const sent = n.sent ?? 0;
  const failed = n.failed ?? 0;
  const notifTotal = Object.values(n).reduce((a, b) => a + b, 0);

  const check = (cond: boolean) => Boolean(o && cond);

  const core: Omit<AdminBadge, "earned">[] = [
    { id: "command", title: "Command Center", description: "Access the admin dashboard", category: "Command", tier: "neon", emoji: "🎖️" },
    { id: "overview", title: "Situation Room", description: "View live KPI overview", category: "Command", tier: "gold", emoji: "📡" },
    { id: "badge-wall", title: "Badge Collector", description: "Inspect your insignia wall", category: "Command", tier: "platinum", emoji: "🏅" },
    { id: "force-sync", title: "Catalog Marshal", description: "Force a catalog sync", category: "Catalog", tier: "gold", emoji: "🔄" },
    { id: "refresh-due", title: "Price Patrol", description: "Refresh due library games", category: "Catalog", tier: "silver", emoji: "⚡" },
    { id: "game-refresh", title: "Single Target", description: "Refresh individual games", category: "Catalog", tier: "bronze", emoji: "🎯" },
    { id: "game-delete", title: "Catalog Purge", description: "Remove games from DB", category: "Catalog", tier: "silver", emoji: "🗑️" },
    { id: "library-view", title: "Shelf Inspector", description: "Browse all user libraries", category: "Catalog", tier: "bronze", emoji: "📚" },
    { id: "user-list", title: "Roster Keeper", description: "List and search users", category: "Users", tier: "bronze", emoji: "👥" },
    { id: "user-delete", title: "Account Terminator", description: "Delete user accounts", category: "Users", tier: "gold", emoji: "☠️" },
    { id: "user-verify", title: "Seal of Approval", description: "Force-verify emails", category: "Users", tier: "silver", emoji: "✅" },
    { id: "resend-verify", title: "Mail Courier", description: "Resend verification links", category: "Users", tier: "bronze", emoji: "📨" },
    { id: "revoke-sessions", title: "Session Breaker", description: "Revoke refresh sessions", category: "Security", tier: "gold", emoji: "🔐" },
    { id: "passkey-view", title: "Keymaster", description: "Inspect all passkeys", category: "Security", tier: "silver", emoji: "🔑" },
    { id: "passkey-revoke", title: "Key Revoker", description: "Delete passkeys globally", category: "Security", tier: "gold", emoji: "🚫" },
    { id: "session-view", title: "Session Watcher", description: "Monitor active sessions", category: "Security", tier: "silver", emoji: "👁️" },
    { id: "watch-list", title: "Alert Overseer", description: "Manage price watches", category: "Alerts", tier: "bronze", emoji: "🔔" },
    { id: "watch-delete", title: "Silence Operator", description: "Delete any watch", category: "Alerts", tier: "silver", emoji: "🔕" },
    { id: "email-log", title: "Postmaster", description: "Read notification log", category: "Email", tier: "bronze", emoji: "📬" },
    { id: "email-purge", title: "Log Janitor", description: "Bulk purge email logs", category: "Email", tier: "silver", emoji: "🧹" },
    { id: "alt-emails", title: "Address Registry", description: "View notification emails", category: "Email", tier: "bronze", emoji: "📧" },
    { id: "health-ping", title: "Pulse Check", description: "Ping health endpoint", category: "Ops", tier: "bronze", emoji: "💓" },
    { id: "scheduler", title: "Clock Keeper", description: "Scheduler awareness", category: "Ops", tier: "silver", emoji: "⏱️" },
    { id: "production", title: "Production Ready", description: "Production mode active", category: "Ops", tier: "platinum", emoji: "🛡️" },
    { id: "smtp", title: "SMTP Wired", description: "Outbound email configured", category: "Ops", tier: "gold", emoji: "📮" },
    { id: "rate-limit", title: "Throttle Guard", description: "Rate limiter online", category: "Ops", tier: "bronze", emoji: "🚦" },
    { id: "db-size", title: "Data Hoarder", description: "Database exceeds 1 MB", category: "Ops", tier: "bronze", emoji: "💾" },
    { id: "activity", title: "Live Feed", description: "Activity stream unlocked", category: "Intel", tier: "silver", emoji: "📊" },
    { id: "top-games", title: "Trend Spotter", description: "Top watched games intel", category: "Intel", tier: "bronze", emoji: "📈" },
    { id: "first-user", title: "Founding Member", description: "At least one user exists", category: "Milestones", tier: "bronze", emoji: "🌱" },
    { id: "users-10", title: "Squad Leader", description: "10+ registered users", category: "Milestones", tier: "silver", emoji: "🎖️" },
    { id: "users-100", title: "Centurion", description: "100+ registered users", category: "Milestones", tier: "gold", emoji: "👑" },
    { id: "games-100", title: "Catalog Scout", description: "100+ games in catalog", category: "Milestones", tier: "bronze", emoji: "🎮" },
    { id: "games-1k", title: "Catalog General", description: "1,000+ games indexed", category: "Milestones", tier: "gold", emoji: "🗄️" },
    { id: "games-10k", title: "Catalog Emperor", description: "10,000+ games indexed", category: "Milestones", tier: "platinum", emoji: "🏛️" },
    { id: "watches-10", title: "Alert Captain", description: "10+ active watches", category: "Milestones", tier: "bronze", emoji: "📣" },
    { id: "watches-100", title: "Alert Admiral", description: "100+ active watches", category: "Milestones", tier: "gold", emoji: "🚨" },
    { id: "emails-100", title: "Courier Class", description: "100+ emails logged", category: "Milestones", tier: "bronze", emoji: "✉️" },
    { id: "emails-1k", title: "Courier Elite", description: "1,000+ emails logged", category: "Milestones", tier: "gold", emoji: "📫" },
    { id: "sent-50", title: "Delivery Ace", description: "50+ emails delivered", category: "Milestones", tier: "silver", emoji: "🕊️" },
    { id: "passkeys-1", title: "WebAuthn Pioneer", description: "First passkey registered", category: "Milestones", tier: "silver", emoji: "🗝️" },
    { id: "library-50", title: "Curator", description: "50+ library entries", category: "Milestones", tier: "bronze", emoji: "📖" },
    { id: "on-sale", title: "Deal Hunter", description: "Games on sale in catalog", category: "Deals", tier: "bronze", emoji: "🏷️" },
    { id: "avg-discount", title: "Bargain Analyst", description: "Average discount tracked", category: "Deals", tier: "silver", emoji: "💰" },
    { id: "history-1k", title: "Price Archivist", description: "1,000+ price history rows", category: "Deals", tier: "silver", emoji: "📉" },
    { id: "unverified-zero", title: "Clean Roster", description: "All users verified", category: "Users", tier: "gold", emoji: "🌟" },
    { id: "zero-failures", title: "Perfect Delivery", description: "No failed emails", category: "Email", tier: "platinum", emoji: "💎" },
    { id: "sync-live", title: "Sync Active", description: "Catalog sync in progress", category: "Catalog", tier: "neon", emoji: "🌀" },
    { id: "locale-us", title: "US Store", description: "en-us store locale", category: "Catalog", tier: "bronze", emoji: "🇺🇸" },
    { id: "startup-sync", title: "Boot Sync", description: "Sync on startup enabled", category: "Ops", tier: "bronze", emoji: "🚀" },
    { id: "verified-majority", title: "Trust Builder", description: "Majority users verified", category: "Users", tier: "silver", emoji: "🤝" },
    { id: "password-auth", title: "Password Corps", description: "Users with passwords", category: "Security", tier: "bronze", emoji: "🔒" },
    { id: "session-army", title: "Session Army", description: "10+ active sessions", category: "Security", tier: "silver", emoji: "⚔️" },
    { id: "alt-email-10", title: "Multi-Inbox", description: "10+ notification emails", category: "Email", tier: "silver", emoji: "📥" },
    { id: "tracked-games", title: "Tracked Intel", description: "User-tracked games exist", category: "Catalog", tier: "bronze", emoji: "📍" },
    { id: "failed-triage", title: "Failure Triage", description: "Failed emails in log", category: "Email", tier: "bronze", emoji: "🩹" },
    { id: "cooldown", title: "Cooldown Respecter", description: "Sync cooldown observed", category: "Catalog", tier: "bronze", emoji: "⏳" },
  ];

  const earnedMap: Record<string, boolean> = {
    command: true,
    overview: true,
    "badge-wall": true,
    "force-sync": true,
    "refresh-due": true,
    "game-refresh": true,
    "game-delete": true,
    "library-view": true,
    "user-list": true,
    "user-delete": true,
    "user-verify": true,
    "resend-verify": true,
    "revoke-sessions": true,
    "passkey-view": true,
    "passkey-revoke": true,
    "session-view": true,
    "watch-list": true,
    "watch-delete": true,
    "email-log": true,
    "email-purge": true,
    "alt-emails": true,
    "health-ping": true,
    scheduler: check(Boolean(s?.scheduler_enabled)),
    production: check(Boolean(s?.production_mode)),
    smtp: check(Boolean(s?.smtp_configured)),
    "rate-limit": check((s?.rate_limit_buckets ?? 0) >= 0),
    "db-size": check((s?.database_bytes ?? 0) > 1024 * 1024),
    activity: check(Boolean(i)),
    "top-games": check((i?.top_watched_games.length ?? 0) > 0),
    "first-user": check((u?.total ?? 0) >= 1),
    "users-10": check((u?.total ?? 0) >= 10),
    "users-100": check((u?.total ?? 0) >= 100),
    "games-100": check((c?.total_games ?? 0) >= 100),
    "games-1k": check((c?.total_games ?? 0) >= 1000),
    "games-10k": check((c?.total_games ?? 0) >= 10000),
    "watches-10": check((w?.enabled ?? 0) >= 10),
    "watches-100": check((w?.enabled ?? 0) >= 100),
    "emails-100": check(notifTotal >= 100),
    "emails-1k": check(notifTotal >= 1000),
    "sent-50": check(sent >= 50),
    "passkeys-1": check((u?.passkeys ?? 0) >= 1),
    "library-50": check((c?.library_entries ?? 0) >= 50),
    "on-sale": check((c?.on_sale ?? 0) > 0),
    "avg-discount": check((i?.avg_discount_percent ?? 0) > 0),
    "history-1k": check((i?.price_history_rows ?? 0) >= 1000),
    "unverified-zero": check((i?.unverified_users ?? 0) === 0 && (u?.total ?? 0) > 0),
    "zero-failures": check(failed === 0 && notifTotal > 0),
    "sync-live": check(Boolean(o?.sync.syncing)),
    "locale-us": check(s?.store_locale === "en-us"),
    "startup-sync": check(Boolean(s?.sync_on_startup)),
    "verified-majority": check((u?.verified ?? 0) > (u?.total ?? 0) / 2),
    "password-auth": check((u?.with_password ?? 0) > 0),
    "session-army": check((u?.active_sessions ?? 0) >= 10),
    "alt-email-10": check((i?.notification_emails ?? 0) >= 10),
    "tracked-games": check((c?.tracked ?? 0) > 0),
    "failed-triage": check(failed > 0),
    cooldown: check(o?.sync.can_refresh === false),
  };

  const badges = core.map((b) => ({ ...b, earned: earnedMap[b.id] ?? false }));

  const fillerCount = Math.min(
    1200,
    Math.max(
      0,
      (u?.total ?? 0) * 12 +
        Math.floor((c?.total_games ?? 0) / 25) +
        (w?.enabled ?? 0) * 3 +
        sent +
        (u?.passkeys ?? 0) * 8 +
        (c?.library_entries ?? 0),
    ),
  );

  const fillerTitles = [
    "Ops", "Intel", "Sync", "Guard", "Scout", "Marshal", "Sentinel", "Watcher",
    "Courier", "Analyst", "Patrol", "Signal", "Vector", "Node", "Relay", "Prime",
  ];
  const fillerEmojis = ["🎖️", "⭐", "🔷", "🔶", "💠", "🛡️", "⚙️", "🔮", "🧭", "📎"];

  for (let n = 0; n < fillerCount; n++) {
    const tier: BadgeTier =
      n % 17 === 0 ? "neon" : n % 11 === 0 ? "platinum" : n % 7 === 0 ? "gold" : n % 3 === 0 ? "silver" : "bronze";
    badges.push({
      id: `filler-${n}`,
      title: `${fillerTitles[n % fillerTitles.length]} #${n + 1}`,
      description: "Decorative service insignia",
      category: "Service Record",
      tier,
      emoji: fillerEmojis[n % fillerEmojis.length],
      earned: true,
    });
  }

  return badges;
}

export function badgeStats(badges: AdminBadge[]) {
  const earned = badges.filter((b) => b.earned).length;
  return { earned, total: badges.length };
}
