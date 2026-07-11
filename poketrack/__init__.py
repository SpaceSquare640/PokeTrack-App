"""PokéTrack — Pokémon GO community activity monitor.

The package is split into three layers that never reach across the wrong way:

* ``poketrack.core``  — data layer: models, database, parser, scheduler, service.
                        Knows nothing about any UI.
* ``poketrack.gui``   — desktop presentation (CustomTkinter).
* ``poketrack.web``   — web presentation (Flask).

Both front-ends talk only to ``core.service.PokeTrackService``.
"""

__version__ = "1.4.1"
