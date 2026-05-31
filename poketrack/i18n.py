"""Internationalisation (i18n).

Every user-facing string lives in ``languages.json`` so translations can be
edited without touching code.  Strings are looked up by dotted path
(e.g. ``"events.view_details"``) and fall back gracefully:

    current language  ->  English  ->  the key itself

so a missing translation degrades visibly but never crashes the UI.  Use
``{placeholder}`` style fields in the JSON and pass them as kwargs to
:meth:`Translator.t`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"


class Translator:
    """Loads ``languages.json`` and resolves translation keys."""

    def __init__(
        self,
        path: str | Path = "languages.json",
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self.path = Path(path)
        self._catalog: dict[str, Any] = {}
        self.language = language
        self.load()
        if self.language not in self._catalog:
            self.language = DEFAULT_LANGUAGE

    def load(self) -> None:
        """Read the translation catalog. Never raises."""
        try:
            self._catalog = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not load translations from %s (%s)", self.path, exc)
            self._catalog = {}

    def set_language(self, language: str) -> None:
        if language in self._catalog:
            self.language = language
        else:
            logger.warning("Language '%s' not available; keeping '%s'", language, self.language)

    def available_languages(self) -> list[str]:
        return list(self._catalog.keys())

    def language_name(self, code: str | None = None) -> str:
        """Human-readable name of a language (always shown in its own script)."""
        code = code or self.language
        return self._lookup(self.language, f"languages.{code}") or code

    def t(self, key: str, **kwargs: Any) -> str:
        """Translate ``key`` in the current language, with safe fallbacks."""
        text = self._lookup(self.language, key)
        if text is None and self.language != DEFAULT_LANGUAGE:
            text = self._lookup(DEFAULT_LANGUAGE, key)
        if text is None:
            return key  # last resort — makes missing keys obvious in the UI
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def _lookup(self, language: str, key: str) -> str | None:
        """Resolve a dotted key within one language; None if not a string leaf."""
        node: Any = self._catalog.get(language)
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node if isinstance(node, str) else None
