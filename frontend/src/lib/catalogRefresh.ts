import { api } from "@/lib/api";

export type CatalogRefreshResult = {
  synced?: boolean;
  syncing?: boolean;
  cooldown?: boolean;
  message?: string;
  retry_after_seconds?: number;
  can_refresh?: boolean;
  last_sync?: string | null;
  catalog_total?: number;
};

export async function refreshCatalogPrices(): Promise<CatalogRefreshResult> {
  return api<CatalogRefreshResult>("/api/catalog/refresh", { method: "POST" });
}

export type SyncStatus = {
  last_sync: string | null;
  catalog_total: number;
  synced_count?: string | null;
  fetched_count?: string | null;
  cooldown_seconds?: number;
  retry_after_seconds?: number;
  can_refresh?: boolean;
  syncing?: boolean;
};

export async function fetchSyncStatus(): Promise<SyncStatus> {
  return api<SyncStatus>("/api/sync-status");
}
