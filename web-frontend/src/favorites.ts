// Favorite toggling without a full page reload: intercept the star form, POST
// via the JSON API, and flip every star of that event type in place. The plain
// form POST remains the no-JS fallback.

import { toggleFavorite } from "./api";
import { showToast } from "./toast";

function applyStar(type: string, fav: boolean): void {
  const stars = document.querySelectorAll<HTMLElement>(
    `[data-fav-form][data-fav-type="${CSS.escape(type)}"] [data-star]`,
  );
  stars.forEach((star) => {
    star.textContent = fav ? "★" : "☆";
    star.style.color = fav ? "var(--mn-warning)" : "var(--mn-text-faint)";
  });
}

export function initFavorites(): void {
  const forms = Array.from(document.querySelectorAll<HTMLFormElement>("[data-fav-form]"));
  for (const form of forms) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const type = form.dataset.favType ?? "";
      const button = form.querySelector<HTMLButtonElement>("[data-star]");
      if (!type || !button) return;
      button.disabled = true;
      try {
        const fav = await toggleFavorite(type);
        applyStar(type, fav);
      } catch {
        showToast("Network error");
      } finally {
        button.disabled = false;
      }
    });
  }
}
