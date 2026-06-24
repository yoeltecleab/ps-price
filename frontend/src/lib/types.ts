export interface Game {
  id: number;
  product_id: string;
  locale: string;
  name: string;
  category: string | null;
  image_url: string | null;
  store_url: string;
  currency: string | null;
  current_price_cents: number | null;
  current_price_formatted: string | null;
  original_price_cents: number | null;
  original_price_formatted: string | null;
  discount_text: string | null;
  availability: string;
  price_source: string | null;
  sale_end_at: string | null;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  platforms: string[];
  discount_percent: number | null;
  is_tracked: boolean;
  catalog_synced_at: string | null;
  description_short: string | null;
  description_long: string | null;
  publisher: string | null;
  release_date: string | null;
  genres: string[];
  features: string[];
  rating_average: number | null;
  rating_count: number | null;
  content_rating: string | null;
  screenshots: string[];
  edition: string | null;
  popularity_rank: number | null;
  savings_cents: number | null;
  created_at: string;
  updated_at: string;
}

export interface PriceHistoryEntry {
  id: number;
  game_id: number;
  price_cents: number | null;
  price_formatted: string | null;
  original_price_cents: number | null;
  discount_text: string | null;
  availability: string;
  checked_at: string;
}

export interface GameDetail extends Game {
  history: PriceHistoryEntry[];
}

export interface SearchResult {
  product_id: string;
  locale: string;
  name: string;
  store_url: string;
  image_url: string | null;
  platforms: string[];
  currency: string | null;
  current_price_cents: number | null;
  current_price_formatted: string | null;
  original_price_cents: number | null;
  original_price_formatted: string | null;
  discount_text: string | null;
  id?: number | null;
  source?: "catalog" | "store";
  discount_percent?: number | null;
  is_tracked?: boolean;
}

export interface SuggestItem {
  id: number;
  name: string;
  product_id: string;
  image_url: string | null;
  current_price_formatted: string | null;
  discount_percent: number | null;
  is_tracked: boolean;
}

export interface DealsPage {
  items: Game[];
  total: number;
  limit: number;
  offset: number;
  last_sync: string | null;
}

export interface Watch {
  id: number;
  game_id: number;
  email: string;
  target_price_cents: number | null;
  notify_on_any_drop: number;
  enabled: number;
  theme_id?: string | null;
  min_drop_cents: number | null;
  min_drop_percent: number | null;
  notification_email_id: number | null;
  last_notified_price_cents: number | null;
  last_notified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: number;
  watch_id: number | null;
  game_id: number | null;
  email: string;
  subject: string;
  body: string;
  status: string;
  reason: string | null;
  error: string | null;
  created_at: string;
  sent_at: string | null;
  game_name: string | null;
}

export type DealSort =
  | "popularity"
  | "discount"
  | "savings"
  | "savings_percent"
  | "price"
  | "original"
  | "rating"
  | "name"
  | "newest";

export type SortDirection = "asc" | "desc";

export interface DealFilters {
  q: string;
  platform: string;
  minDiscount: number;
  maxPrice: string;
  sort: DealSort;
  sortDir: SortDirection;
  onSaleOnly: boolean;
}

export interface AuthUser {
  id: number;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  has_password: boolean;
  is_admin: boolean;
  preferred_theme_id?: string | null;
}

export interface NotificationEmail {
  id: number;
  email: string;
  label: string | null;
  verified: boolean;
  is_primary: boolean;
  created_at: string;
}

export interface Passkey {
  id: number;
  friendly_name: string | null;
  created_at: string;
  last_used_at?: string | null;
}

export interface MeResponse {
  user: AuthUser;
  notification_emails: NotificationEmail[];
  passkeys: Passkey[];
}
