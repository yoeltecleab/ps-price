import { NextResponse } from "next/server";

const apiUrl = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";
const internalKey = process.env.INTERNAL_API_KEY || "";

export async function GET() {
  const headers: HeadersInit = {};
  if (internalKey) {
    headers["X-PS-Price-Internal"] = internalKey;
  }
  const res = await fetch(`${apiUrl}/healthz`, { headers, cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
