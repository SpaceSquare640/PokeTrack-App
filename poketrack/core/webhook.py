"""Outgoing webhooks for new-event alerts.

The webhook URL is user-configurable (``config.json`` → ``webhook_url`` / the
Settings tab). When new events appear in the user's selected regions, PokéTrack
POSTs a JSON payload to that URL.

Payload shape adapts to the destination so the common targets "just work":

* **Discord**  (`discord.com/api/webhooks/…`)  → ``{content, embeds[]}``
* **Slack**    (`hooks.slack.com/…`)            → ``{text}``
* **Anything else**                              → ``{content, text, title, events[]}``
  (includes a structured ``events`` array for custom consumers)

All network errors are caught and returned as ``(False, reason)`` — a bad
webhook never disrupts a refresh.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .http import SESSION

logger = logging.getLogger(__name__)


def _provider(url: str) -> str:
    u = url.lower()
    if "discord.com/api/webhooks" in u or "discordapp.com/api/webhooks" in u:
        return "discord"
    if "hooks.slack.com" in u:
        return "slack"
    return "generic"


def build_payload(url: str, title: str, message: str, events: list[dict]) -> tuple[dict, str]:
    """Build the provider-appropriate JSON body. Pure function — easy to test."""
    provider = _provider(url)
    bullet_lines = [
        f"• {e.get('name', '')}" + (f" — {e['link']}" if e.get("link") else "")
        for e in events[:10]
    ]
    text = message + (("\n" + "\n".join(bullet_lines)) if bullet_lines else "")

    if provider == "discord":
        embeds: list[dict[str, Any]] = []
        for e in events[:10]:
            embed: dict[str, Any] = {"title": (e.get("name") or "")[:240]}
            if e.get("link"):
                embed["url"] = e["link"]
            desc = e.get("description") or e.get("region") or ""
            if desc:
                embed["description"] = desc[:300]
            embeds.append(embed)
        return {"content": message[:1900], "embeds": embeds}, provider

    if provider == "slack":
        return {"text": text[:3000]}, provider

    # Generic: include both content/text aliases plus structured data.
    return {"content": message, "text": text, "title": title, "events": events[:25]}, provider


def send(url: str, title: str, message: str, events: list[dict], timeout: int = 10) -> tuple[bool, str]:
    """POST the alert. Returns ``(ok, detail)`` and never raises."""
    if not url:
        return False, "no url configured"
    payload, provider = build_payload(url, title, message, events)
    try:
        resp = SESSION.post(url, json=payload, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning("Webhook POST returned %s", resp.status_code)
        return ok, f"{provider}:{resp.status_code}"
    except requests.RequestException as exc:
        logger.warning("Webhook POST failed: %s", exc)
        return False, str(exc)
