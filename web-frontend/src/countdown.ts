// Live countdown timers — recomputes each card's relative-time string every
// second so "Starts in 3h" / "Ends in 2d" stay accurate without a reload, and
// flips upcoming -> active the moment an event begins.
//
// Mirrors the Python logic (poketrack.core.service.countdown + _humanize and
// Event.status). Datetimes are naive-local ISO strings; `new Date(iso)` parses
// a timezone-less datetime as local time, matching the Python naive-local model.

import type { I18n } from "./types";

function humanize(i18n: I18n, deltaMs: number): string {
  const secs = Math.max(0, Math.floor(deltaMs / 1000));
  const days = Math.floor(secs / 86_400);
  if (days >= 1) return i18n.day.replace("{n}", String(days));
  const hours = Math.floor(secs / 3_600);
  if (hours >= 1) return i18n.hour.replace("{n}", String(hours));
  const minutes = Math.floor((secs % 3_600) / 60);
  if (minutes >= 1) return i18n.minute.replace("{n}", String(minutes));
  return i18n.now;
}

type Status = "upcoming" | "active" | "ended" | "unknown";

function statusOf(now: number, start: number | null, end: number | null): Status {
  if (start !== null && now < start) return "upcoming";
  if (end !== null && now > end) return "ended";
  if (start !== null && start <= now && (end === null || now <= end)) return "active";
  return "unknown";
}

function parse(value: string | null): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

function render(el: HTMLElement, i18n: I18n, now: number): void {
  const start = parse(el.dataset.start ?? null);
  const end = parse(el.dataset.end ?? null);
  const status = statusOf(now, start, end);
  let text = "";
  if (status === "upcoming" && start !== null) {
    text = i18n.starts_in.replace("{time}", humanize(i18n, start - now));
  } else if (status === "active" && end !== null) {
    text = i18n.ends_in.replace("{time}", humanize(i18n, end - now));
  } else if (status === "ended") {
    text = i18n.ended;
  }
  el.textContent = text;
}

export function initCountdowns(i18n: I18n): void {
  const els = Array.from(document.querySelectorAll<HTMLElement>("[data-countdown]"));
  if (els.length === 0) return;
  const tick = () => {
    const now = Date.now();
    for (const el of els) render(el, i18n, now);
  };
  tick();
  window.setInterval(tick, 1_000);
}
