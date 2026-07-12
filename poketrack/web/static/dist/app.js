async function w() {
  const t = await fetch("/api/refresh", { method: "POST" });
  if (!t.ok) throw new Error(`refresh failed: ${t.status}`);
  return await t.json();
}
async function g(t, e, n = "") {
  const o = new URLSearchParams();
  t && o.set("q", t), e && o.set("type", e), n && o.set("status", n);
  const r = o.toString(), s = await fetch("/api/events" + (r ? "?" + r : ""));
  if (!s.ok) throw new Error(`events failed: ${s.status}`);
  const a = await s.json();
  return Array.isArray(a) ? a : [];
}
async function v(t) {
  const e = await fetch("/api/favorite", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ type: t }).toString()
  });
  if (!e.ok) throw new Error(`favorite failed: ${e.status}`);
  return !!(await e.json()).favorite;
}
let d = null;
function l(t, e = !1) {
  const n = document.getElementById("toast");
  return n ? (n.textContent = t, n.classList.add("toast-show"), d !== null && window.clearTimeout(d), n.style.cursor = "default", n.onclick = null, e || (d = window.setTimeout(() => n.classList.remove("toast-show"), 2500)), n) : null;
}
function m(t, e) {
  const n = Math.max(0, Math.floor(e / 1e3)), o = Math.floor(n / 86400);
  if (o >= 1) return t.day.replace("{n}", String(o));
  const r = Math.floor(n / 3600);
  if (r >= 1) return t.hour.replace("{n}", String(r));
  const s = Math.floor(n % 3600 / 60);
  return s >= 1 ? t.minute.replace("{n}", String(s)) : t.now;
}
function S(t, e, n) {
  return e !== null && t < e ? "upcoming" : n !== null && t > n ? "ended" : e !== null && e <= t && (n === null || t <= n) ? "active" : "unknown";
}
function y(t) {
  if (!t) return null;
  const e = new Date(t).getTime();
  return Number.isNaN(e) ? null : e;
}
function E(t, e, n) {
  const o = y(t.dataset.start ?? null), r = y(t.dataset.end ?? null), s = S(n, o, r);
  let a = "";
  s === "upcoming" && o !== null ? a = e.starts_in.replace("{time}", m(e, o - n)) : s === "active" && r !== null ? a = e.ends_in.replace("{time}", m(e, r - n)) : s === "ended" && (a = e.ended), t.textContent = a;
}
function k(t) {
  const e = Array.from(document.querySelectorAll("[data-countdown]"));
  if (e.length === 0) return;
  const n = () => {
    const o = Date.now();
    for (const r of e) E(r, t, o);
  };
  n(), window.setInterval(n, 1e3);
}
function L() {
  const t = document.querySelector('input[name="q"]');
  if (!t) return;
  const e = Array.from(document.querySelectorAll("[data-event-card]"));
  if (e.length === 0) return;
  const n = Array.from(document.querySelectorAll("[data-event-section]")), o = document.querySelector("[data-empty-hint]"), r = () => {
    const s = t.value.trim().toLowerCase();
    let a = 0;
    for (const i of e) {
      const u = i.dataset.search ?? "", c = s === "" || u.includes(s);
      i.style.display = c ? "" : "none", c && (a += 1);
    }
    for (const i of n) {
      const u = i.dataset.eventSection, c = e.some(
        (f) => f.dataset.group === u && f.style.display !== "none"
      );
      i.style.display = c ? "" : "none";
    }
    o && (o.style.display = a === 0 ? "" : "none");
  };
  t.addEventListener("input", r);
}
function q(t, e) {
  document.querySelectorAll(
    `[data-fav-form][data-fav-type="${CSS.escape(t)}"] [data-star]`
  ).forEach((o) => {
    o.textContent = e ? "★" : "☆", o.style.color = e ? "var(--mn-warning)" : "var(--mn-text-faint)", o.closest("button")?.setAttribute("aria-pressed", String(e));
  });
}
function A() {
  const t = Array.from(document.querySelectorAll("[data-fav-form]"));
  for (const e of t)
    e.addEventListener("submit", async (n) => {
      n.preventDefault();
      const o = e.dataset.favType ?? "", r = e.querySelector("[data-star]");
      if (!(!o || !r)) {
        r.disabled = !0;
        try {
          const s = await v(o);
          q(o, s);
        } catch {
          l("Network error");
        } finally {
          r.disabled = !1;
        }
      }
    });
}
const b = "poketrack-theme";
function T(t) {
  document.documentElement.classList.toggle("light", t);
  try {
    localStorage.setItem(b, t ? "light" : "dark");
  } catch {
  }
}
function h(t) {
  const e = document.documentElement.classList.contains("light");
  t.querySelector("[data-theme-dark]")?.classList.toggle("on", !e), t.querySelector("[data-theme-light]")?.classList.toggle("on", e), t.setAttribute("aria-pressed", String(e));
}
function C() {
  const t = document.querySelector("[data-theme-toggle]");
  t && (h(t), t.addEventListener("click", () => {
    T(!document.documentElement.classList.contains("light")), h(t);
  }));
}
const x = {
  starts_in: "Starts in {time}",
  ends_in: "Ends in {time}",
  ended: "Ended",
  day: "{n}d",
  hour: "{n}h",
  minute: "{n}m",
  now: "moments"
};
function I() {
  const t = window.POKETRACK;
  return {
    count: t?.count ?? 0,
    q: t?.q ?? "",
    type: t?.type ?? "",
    status: t?.status ?? "",
    i18n: { ...x, ...t?.i18n ?? {} }
  };
}
function D() {
  const t = document.getElementById("refresh-btn");
  if (!t) return;
  const e = t.textContent ?? "";
  t.addEventListener("click", async () => {
    t.disabled = !0, t.style.opacity = "0.6", t.textContent = "…";
    try {
      const n = await w();
      l(n.message || "Done"), window.setTimeout(() => window.location.reload(), 700);
    } catch {
      l("Network error"), t.disabled = !1, t.style.opacity = "1", t.textContent = e;
    }
  });
}
function M(t) {
  const e = async () => {
    try {
      const n = await g(t.q, t.type, t.status);
      if (n.length > t.count) {
        const o = l(`↻ ${n.length - t.count} new — click to update`, !0);
        o && (o.style.cursor = "pointer", o.onclick = () => window.location.reload());
      }
    } catch {
    }
  };
  window.setInterval(e, 6e4);
}
function N() {
  "serviceWorker" in navigator && navigator.serviceWorker.register("/sw.js").catch(() => {
  });
}
function p() {
  const t = I();
  k(t.i18n), L(), A(), C(), D(), M(t), N();
}
document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", p) : p();
