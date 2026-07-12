// Light/dark theme toggle. The saved choice is applied before first paint by
// an inline <head> script in base.html; this module wires the toggle button
// and keeps its pressed-state in sync.

const KEY = "poketrack-theme";

function apply(light: boolean): void {
  document.documentElement.classList.toggle("light", light);
  try {
    localStorage.setItem(KEY, light ? "light" : "dark");
  } catch {
    /* storage unavailable (private mode) — theme still applies for this page */
  }
}

function syncButton(button: HTMLElement): void {
  const light = document.documentElement.classList.contains("light");
  button.querySelector("[data-theme-dark]")?.classList.toggle("on", !light);
  button.querySelector("[data-theme-light]")?.classList.toggle("on", light);
  button.setAttribute("aria-pressed", String(light));
}

export function initThemeToggle(): void {
  const button = document.querySelector<HTMLElement>("[data-theme-toggle]");
  if (!button) return;
  syncButton(button);
  button.addEventListener("click", () => {
    apply(!document.documentElement.classList.contains("light"));
    syncButton(button);
  });
}
