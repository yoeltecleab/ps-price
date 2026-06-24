/** Header the browser client sends so the Next.js proxy can reject direct /api URL visits. */
export const API_CLIENT_HEADER = "X-PS-Price-Client";
export const API_CLIENT_VALUE = "1";

export function applyApiClientHeaders(headers: Headers): void {
  headers.set(API_CLIENT_HEADER, API_CLIENT_VALUE);
}
