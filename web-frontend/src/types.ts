// Shared types for the PokéTrack web front-end.

/** Countdown/relative-time templates, injected from languages.json (raw, with
 *  `{time}` / `{n}` placeholders still intact). */
export interface I18n {
  starts_in: string;
  ends_in: string;
  ended: string;
  day: string;
  hour: string;
  minute: string;
  now: string;
}

/** Bootstrap state the server renders into the page (`window.POKETRACK`). */
export interface PokeTrackState {
  count: number;
  q: string;
  type: string;
  i18n: I18n;
}

/** One event as returned by `GET /api/events` (a subset of the view model). */
export interface EventVM {
  event_id: string;
  name: string;
  event_type: string;
  status: string;
}

/** Response of `POST /api/refresh`. */
export interface RefreshResult {
  ok: boolean;
  count: number;
  new: number;
  message: string;
}

declare global {
  interface Window {
    POKETRACK?: PokeTrackState;
  }
}
