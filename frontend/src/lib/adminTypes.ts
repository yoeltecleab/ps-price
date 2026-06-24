export interface AdminOverview {
  users: {
    total: number;
    verified: number;
    with_password: number;
    passkeys: number;
    active_sessions: number;
  };
  catalog: {
    total_games: number;
    on_sale: number;
    tracked: number;
    library_entries: number;
  };
  watches: {
    total: number;
    enabled: number;
  };
  notifications: Record<string, number>;
  sync: {
    last_sync: string | null;
    catalog_total: number;
    syncing?: boolean;
    can_refresh?: boolean;
    retry_after_seconds?: number;
  };
  insights: AdminInsights;
  system: {
    scheduler_enabled: boolean;
    sync_on_startup: boolean;
    smtp_configured: boolean;
    store_locale: string;
    production_mode: boolean;
    database_backend: string;
    database_bytes: number;
    database_url_set: boolean;
    rate_limit_buckets: number;
    check_interval_minutes: number;
    feed_sync_interval_minutes: number;
  };
}

export interface AdminInsights {
  recent_users: {
    id: number;
    email: string;
    display_name: string | null;
    email_verified_at: string | null;
    created_at: string;
  }[];
  top_watched_games: {
    id: number;
    name: string;
    current_price_formatted: string | null;
    watch_count: number;
  }[];
  recent_watches: {
    id: number;
    created_at: string;
    game_name: string;
    user_email: string | null;
  }[];
  recent_emails: {
    id: number;
    email: string;
    subject: string;
    status: string;
    created_at: string;
    game_name: string | null;
  }[];
  price_history_rows: number;
  unverified_users: number;
  notification_emails: number;
  avg_discount_percent: number;
}

export interface AdminUserRow {
  id: number;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  has_password: boolean;
  library_count: number;
  watch_count: number;
  passkey_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminWatchRow {
  id: number;
  game_id: number;
  game_name: string;
  user_email: string | null;
  email: string;
  enabled: number;
  notify_on_any_drop: number;
  target_price_cents: number | null;
  current_price_formatted: string | null;
  store_url: string;
  created_at: string;
  last_notified_at: string | null;
}

export interface AdminNotificationRow {
  id: number;
  email: string;
  subject: string;
  body: string;
  status: string;
  reason: string | null;
  error: string | null;
  game_name: string | null;
  user_email: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface AdminGameRow {
  id: number;
  name: string;
  current_price_formatted: string | null;
  discount_percent: number | null;
  is_tracked: number;
  locale: string;
  updated_at: string;
}

export interface AdminLibraryRow {
  user_id: number;
  game_id: number;
  game_name: string;
  user_email: string;
  current_price_formatted: string | null;
  discount_percent: number | null;
  created_at: string;
}

export interface AdminSessionRow {
  id: number;
  user_id: number;
  user_email: string;
  expires_at: string;
  created_at: string;
  user_agent: string | null;
  ip_address: string | null;
}

export interface AdminPasskeyRow {
  id: number;
  user_id: number;
  user_email: string;
  friendly_name: string | null;
  transports: string | null;
  sign_count: number;
  created_at: string;
  last_used_at: string | null;
}

export interface AdminNotificationEmailRow {
  id: number;
  user_id: number;
  user_email: string;
  email: string;
  label: string | null;
  verified: boolean;
  is_primary: boolean;
  created_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
