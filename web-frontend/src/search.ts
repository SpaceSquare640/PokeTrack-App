// Instant client-side search: filter the already-rendered event cards as the
// user types, with no round-trip. The server-side search form still works as a
// no-JS fallback (and for sharing filtered URLs); this just makes it live.

export function initInstantSearch(): void {
  const input = document.querySelector<HTMLInputElement>('input[name="q"]');
  if (!input) return;
  const cards = Array.from(document.querySelectorAll<HTMLElement>("[data-event-card]"));
  if (cards.length === 0) return;

  const sections = Array.from(document.querySelectorAll<HTMLElement>("[data-event-section]"));
  const empty = document.querySelector<HTMLElement>("[data-empty-hint]");

  const apply = () => {
    const term = input.value.trim().toLowerCase();
    let visible = 0;
    for (const card of cards) {
      const hay = card.dataset.search ?? "";
      const show = term === "" || hay.includes(term);
      card.style.display = show ? "" : "none";
      if (show) visible += 1;
    }
    // Hide a section heading when all of its cards are filtered out.
    for (const section of sections) {
      const group = section.dataset.eventSection;
      const anyVisible = cards.some(
        (c) => c.dataset.group === group && c.style.display !== "none",
      );
      section.style.display = anyVisible ? "" : "none";
    }
    if (empty) empty.style.display = visible === 0 ? "" : "none";
  };

  input.addEventListener("input", apply);
}
