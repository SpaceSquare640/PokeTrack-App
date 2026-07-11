"""Benchmark the Rust fast path against the pure-Python data path.

Run from the project root (after installing the extension — see README):

    python poketrack-native/benchmark.py            # synthetic feeds
    python poketrack-native/benchmark.py --live      # + the real ScrapedDuck feed

Reports three numbers per feed size:

* **pure Python**       — ``json.loads`` + ``Event.from_scrapedduck`` per record.
* **native + Event**    — Rust ``parse_feed`` then ``Event.from_native`` per record.
* **native raw**        — Rust ``parse_feed`` only (JSON → list of dicts).

The honest story: Rust does the JSON→structured-data step several times faster,
but building Python ``Event`` objects (+ datetime normalisation) is unavoidable
Python work that narrows the end-to-end gap. The gap widens as feeds grow.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poketrack.core import native, regions  # noqa: E402
from poketrack.core.models import Event  # noqa: E402
from poketrack.core.parser import LeekDuckSource  # noqa: E402

_TEMPLATE = {
    "eventID": "ev-{i}", "name": "Community Day {i}", "eventType": "community-day",
    "heading": "Community Day", "link": "https://x/{i}", "image": "https://img/{i}.png",
    "start": "2099-05-19T14:00:00.000", "end": "2099-05-19T17:00:00.000",
    "extraData": {
        "raidbattles": {"bosses": [{"name": "Pikachu"}, {"name": "Raichu"}]},
        "promocodes": ["FREE{i}"],
        "generic": {"hasSpawns": True, "hasFieldResearchTasks": True},
    },
}


def synth_feed(n: int) -> str:
    """A synthetic feed of ``n`` records as raw JSON text."""
    items = []
    for i in range(n):
        raw = json.dumps(_TEMPLATE).replace("{i}", str(i))
        items.append(json.loads(raw))
    return json.dumps(items)


def _bench(fn, iters: int) -> tuple[float, float]:
    for _ in range(5):  # warmup
        fn()
    samples = []
    for _ in range(iters):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return statistics.mean(samples), statistics.median(samples)


def run(text: str, label: str, iters: int) -> None:
    src = LeekDuckSource()
    kw = regions.keyword_pairs()

    def py_path():
        return src._parse_feed(json.loads(text))

    def native_path():
        return [Event.from_native(r) for r in native.parse_feed(text, kw)]

    def native_raw():
        return native.parse_feed(text, kw)

    n = len(json.loads(text))
    assert len(py_path()) == n
    pm, _ = _bench(py_path, iters)
    print(f"\n{label} — {n} events ({len(text):,} bytes), {iters} iters")
    print(f"  {'pure Python':22} {pm:8.3f} ms")
    if native.AVAILABLE:
        assert len(native_path()) == n
        nm, _ = _bench(native_path, iters)
        rm, _ = _bench(native_raw, iters)
        print(f"  {'native + Event build':22} {nm:8.3f} ms   ({pm / nm:.1f}x)")
        print(f"  {'native raw (dicts)':22} {rm:8.3f} ms   ({pm / rm:.1f}x)")
    else:
        print("  native: NOT INSTALLED — pure-Python fallback only")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="also benchmark the real feed")
    ap.add_argument("--iters", type=int, default=300)
    args = ap.parse_args()

    print(f"native available: {native.AVAILABLE}" + (f" (v{native.VERSION})" if native.AVAILABLE else ""))
    for size in (40, 400, 4000):
        run(synth_feed(size), f"synthetic x{size}", args.iters)

    if args.live:
        import urllib.request
        url = "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json"
        text = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
        run(text, "live ScrapedDuck feed", args.iters)


if __name__ == "__main__":
    main()
