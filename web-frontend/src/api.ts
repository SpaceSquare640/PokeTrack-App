// Typed client for the PokéTrack JSON API.

import type { EventVM, RefreshResult } from "./types";

/** Trigger a server-side fetch of the source feed. */
export async function triggerRefresh(): Promise<RefreshResult> {
  const resp = await fetch("/api/refresh", { method: "POST" });
  if (!resp.ok) throw new Error(`refresh failed: ${resp.status}`);
  return (await resp.json()) as RefreshResult;
}

/** Read the currently-stored events (optionally filtered by search/type). */
export async function fetchEvents(q: string, type: string, status = ""): Promise<EventVM[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (type) params.set("type", type);
  if (status) params.set("status", status);
  const qs = params.toString();
  const resp = await fetch("/api/events" + (qs ? "?" + qs : ""));
  if (!resp.ok) throw new Error(`events failed: ${resp.status}`);
  const data: unknown = await resp.json();
  return Array.isArray(data) ? (data as EventVM[]) : [];
}

/** Toggle a favorited event type; returns the new favorited state. */
export async function toggleFavorite(eventType: string): Promise<boolean> {
  const resp = await fetch("/api/favorite", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ type: eventType }).toString(),
  });
  if (!resp.ok) throw new Error(`favorite failed: ${resp.status}`);
  const data = (await resp.json()) as { favorite: boolean };
  return Boolean(data.favorite);
}
