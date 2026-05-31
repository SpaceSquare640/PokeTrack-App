/*
 * PokéTrack web — front-end behaviour.
 *  - "Refresh" button: triggers a server-side fetch, then reloads.
 *  - Background poller: every 60s checks /api/events (which reads the locally
 *    stored data the server's scheduler keeps fresh) and offers a one-click
 *    reload when new events appear, without disrupting what you're reading.
 */
(function () {
  "use strict";

  const refreshBtn = document.getElementById("refresh-btn");
  const toast = document.getElementById("toast");
  const state = window.POKETRACK || { count: 0, q: "", type: "" };
  let toastTimer = null;

  function showToast(message, persistent) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("toast-show");
    if (toastTimer) window.clearTimeout(toastTimer);
    if (!persistent) {
      toastTimer = window.setTimeout(() => toast.classList.remove("toast-show"), 2500);
    }
  }

  // Manual refresh: ask the server to fetch, then reload to re-render.
  async function refresh() {
    if (!refreshBtn) return;
    const original = refreshBtn.textContent;
    refreshBtn.disabled = true;
    refreshBtn.style.opacity = "0.6";
    refreshBtn.textContent = "…";
    try {
      const resp = await fetch("/api/refresh", { method: "POST" });
      const data = await resp.json();
      showToast(data.message || "Done");
      window.setTimeout(() => window.location.reload(), 700);
    } catch (err) {
      showToast("Network error");
      refreshBtn.disabled = false;
      refreshBtn.style.opacity = "1";
      refreshBtn.textContent = original;
    }
  }

  if (refreshBtn) refreshBtn.addEventListener("click", refresh);

  // Background poll — non-intrusive; only nudges when the count grows.
  function buildQuery() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.type) params.set("type", state.type);
    const qs = params.toString();
    return "/api/events" + (qs ? "?" + qs : "");
  }

  async function poll() {
    try {
      const resp = await fetch(buildQuery());
      const events = await resp.json();
      if (Array.isArray(events) && events.length > state.count) {
        const toastEl = toast;
        showToast("↻ " + (events.length - state.count) + " new — click to update", true);
        if (toastEl) {
          toastEl.style.cursor = "pointer";
          toastEl.onclick = () => window.location.reload();
        }
      }
    } catch (err) {
      /* offline or transient — ignore; cached page stays usable */
    }
  }

  window.setInterval(poll, 60000);
})();
