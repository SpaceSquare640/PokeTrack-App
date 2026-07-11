// PokéTrack web front-end (TypeScript, bundled by Vite).
//
// Progressive enhancement over the Flask server-rendered page: the page works
// without JavaScript; this layer adds live countdowns, instant search, no-reload
// favorites, an async refresh button, and a non-intrusive new-events poller.

import { triggerRefresh, fetchEvents } from "./api";
import { showToast } from "./toast";
import { initCountdowns } from "./countdown";
import { initInstantSearch } from "./search";
import { initFavorites } from "./favorites";
import type { PokeTrackState } from "./types";

const DEFAULT_I18N = {
  starts_in: "Starts in {time}",
  ends_in: "Ends in {time}",
  ended: "Ended",
  day: "{n}d",
  hour: "{n}h",
  minute: "{n}m",
  now: "moments",
};

function getState(): PokeTrackState {
  const s = window.POKETRACK;
  return {
    count: s?.count ?? 0,
    q: s?.q ?? "",
    type: s?.type ?? "",
    status: s?.status ?? "",
    i18n: { ...DEFAULT_I18N, ...(s?.i18n ?? {}) },
  };
}

/** Manual refresh: ask the server to fetch, then reload to re-render (SSR). */
function initRefreshButton(): void {
  const button = document.getElementById("refresh-btn") as HTMLButtonElement | null;
  if (!button) return;
  const original = button.textContent ?? "";
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.style.opacity = "0.6";
    button.textContent = "…";
    try {
      const result = await triggerRefresh();
      showToast(result.message || "Done");
      window.setTimeout(() => window.location.reload(), 700);
    } catch {
      showToast("Network error");
      button.disabled = false;
      button.style.opacity = "1";
      button.textContent = original;
    }
  });
}

/** Background poll — nudges (once) when the stored event count grows. */
function initPoller(state: PokeTrackState): void {
  const poll = async () => {
    try {
      const events = await fetchEvents(state.q, state.type, state.status);
      if (events.length > state.count) {
        const toast = showToast(`↻ ${events.length - state.count} new — click to update`, true);
        if (toast) {
          toast.style.cursor = "pointer";
          toast.onclick = () => window.location.reload();
        }
      }
    } catch {
      /* offline/transient — the cached page stays usable */
    }
  };
  window.setInterval(poll, 60_000);
}

function main(): void {
  const state = getState();
  initCountdowns(state.i18n);
  initInstantSearch();
  initFavorites();
  initRefreshButton();
  initPoller(state);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
