# API Reference

Base URL: `http://127.0.0.1:8000`

## Health

`GET /healthz`

Returns service, database, scheduler, and email configuration status.

## Search

`GET /api/search?q={query}&locale=en-us&limit=10`

Searches PlayStation Store server-rendered search results and returns product IDs, names, platforms, images, and current visible prices when present in the search payload.

## Games

`POST /api/games`

Adds or refreshes a tracked product. `product_ref` may be either a full PlayStation Store product URL or a product ID.

```json
{
  "product_ref": "UP9000-PPSA08329_00-GOWRAGNAROK00000",
  "locale": "en-us"
}
```

`GET /api/games`

Lists tracked games with current stored price and last fetch status.

`GET /api/games/{game_id}`

Returns one tracked game and recent price history.

`POST /api/games/{game_id}/refresh`

Forces a live refresh for one game, bypassing the in-process cache.

`DELETE /api/games/{game_id}`

Deletes a tracked game, its watches, history, and notification log entries.

## Watches

`POST /api/watches`

Creates an email watch. `target_price_cents` is optional. If `notify_on_any_drop` is true, a notification is sent when a later refresh sees a lower price than the previous stored price.

```json
{
  "game_id": 1,
  "email": "you@example.com",
  "target_price_cents": 2999,
  "notify_on_any_drop": true,
  "enabled": true
}
```

`GET /api/watches`

Lists watches. Pass `?game_id=1` to filter.

`PATCH /api/watches/{watch_id}`

Updates target price, drop notification behavior, or enabled state.

`DELETE /api/watches/{watch_id}`

Deletes a watch.

`POST /api/watches/{watch_id}/test`

Sends a test email for a watch when SMTP is configured. If SMTP is not configured, a skipped notification is logged.

## Notifications

`GET /api/notifications?limit=50`

Lists recent notification attempts with `sent`, `failed`, or `skipped` status.

## Operations

`POST /api/refresh-due`

Runs the same due-game refresh pass used by the background scheduler.
