async function p() {
  const t = await fetch("/api/refresh", { method: "POST" });
  if (!t.ok) throw new Error(`refresh failed: ${t.status}`);
  return await t.json();
}
async function h(t, e, n = "") {
  const o = new URLSearchParams();
  t && o.set("q", t), e && o.set("type", e), n && o.set("status", n);
  const r = o.toString(), a = await fetch("/api/events" + (r ? "?" + r : ""));
  if (!a.ok) throw new Error(`events failed: ${a.status}`);
  const s = await a.json();
  return Array.isArray(s) ? s : [];
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
  const a = Math.floor(n % 3600 / 60);
  return a >= 1 ? t.minute.replace("{n}", String(a)) : t.now;
}
function g(t, e, n) {
  return e !== null && t < e ? "upcoming" : n !== null && t > n ? "ended" : e !== null && e <= t && (n === null || t <= n) ? "active" : "unknown";
}
function y(t) {
  if (!t) return null;
  const e = new Date(t).getTime();
  return Number.isNaN(e) ? null : e;
}
function S(t, e, n) {
  const o = y(t.dataset.start ?? null), r = y(t.dataset.end ?? null), a = g(n, o, r);
  let s = "";
  a === "upcoming" && o !== null ? s = e.starts_in.replace("{time}", m(e, o - n)) : a === "active" && r !== null ? s = e.ends_in.replace("{time}", m(e, r - n)) : a === "ended" && (s = e.ended), t.textContent = s;
}
function E(t) {
  const e = Array.from(document.querySelectorAll("[data-countdown]"));
  if (e.length === 0) return;
  const n = () => {
    const o = Date.now();
    for (const r of e) S(r, t, o);
  };
  n(), window.setInterval(n, 1e3);
}
function q() {
  const t = document.querySelector('input[name="q"]');
  if (!t) return;
  const e = Array.from(document.querySelectorAll("[data-event-card]"));
  if (e.length === 0) return;
  const n = Array.from(document.querySelectorAll("[data-event-section]")), o = document.querySelector("[data-empty-hint]"), r = () => {
    const a = t.value.trim().toLowerCase();
    let s = 0;
    for (const i of e) {
      const u = i.dataset.search ?? "", c = a === "" || u.includes(a);
      i.style.display = c ? "" : "none", c && (s += 1);
    }
    for (const i of n) {
      const u = i.dataset.eventSection, c = e.some(
        (f) => f.dataset.group === u && f.style.display !== "none"
      );
      i.style.display = c ? "" : "none";
    }
    o && (o.style.display = s === 0 ? "" : "none");
  };
  t.addEventListener("input", r);
}
function A(t, e) {
  document.querySelectorAll(
    `[data-fav-form][data-fav-type="${CSS.escape(t)}"] [data-star]`
  ).forEach((o) => {
    o.textContent = e ? "★" : "☆", o.style.color = e ? "var(--mn-warning)" : "var(--mn-text-faint)";
  });
}
function b() {
  const t = Array.from(document.querySelectorAll("[data-fav-form]"));
  for (const e of t)
    e.addEventListener("submit", async (n) => {
      n.preventDefault();
      const o = e.dataset.favType ?? "", r = e.querySelector("[data-star]");
      if (!(!o || !r)) {
        r.disabled = !0;
        try {
          const a = await v(o);
          A(o, a);
        } catch {
          l("Network error");
        } finally {
          r.disabled = !1;
        }
      }
    });
}
const C = {
  starts_in: "Starts in {time}",
  ends_in: "Ends in {time}",
  ended: "Ended",
  day: "{n}d",
  hour: "{n}h",
  minute: "{n}m",
  now: "moments"
};
function k() {
  const t = window.POKETRACK;
  return {
    count: t?.count ?? 0,
    q: t?.q ?? "",
    type: t?.type ?? "",
    status: t?.status ?? "",
    i18n: { ...C, ...t?.i18n ?? {} }
  };
}
function L() {
  const t = document.getElementById("refresh-btn");
  if (!t) return;
  const e = t.textContent ?? "";
  t.addEventListener("click", async () => {
    t.disabled = !0, t.style.opacity = "0.6", t.textContent = "…";
    try {
      const n = await p();
      l(n.message || "Done"), window.setTimeout(() => window.location.reload(), 700);
    } catch {
      l("Network error"), t.disabled = !1, t.style.opacity = "1", t.textContent = e;
    }
  });
}
function T(t) {
  const e = async () => {
    try {
      const n = await h(t.q, t.type, t.status);
      if (n.length > t.count) {
        const o = l(`↻ ${n.length - t.count} new — click to update`, !0);
        o && (o.style.cursor = "pointer", o.onclick = () => window.location.reload());
      }
    } catch {
    }
  };
  window.setInterval(e, 6e4);
}
function w() {
  const t = k();
  E(t.i18n), q(), b(), L(), T(t);
}
document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", w) : w();
