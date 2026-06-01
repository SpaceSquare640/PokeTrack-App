"""Outgoing webhooks for new-event alerts.

The webhook URL is user-configurable (``config.json`` → ``webhook_url`` / the
Settings tab). When new events appear in the user's selected regions, PokéTrack
POSTs a JSON payload to that URL.

Payload shape adapts to the destination so common targets "just work":

* **Discord**  (`discord.com/api/webhooks/…`)  → ``{content, embeds[]}``
* **Slack**    (`hooks.slack.com/…`)            → ``{text}``
* **Anything else**                              → ``{content, text, title, events[]}``

**Security (HMAC).** If a ``webhook_secret`` is configured, every POST is signed
with an ``X-PokeTrack-Signature: sha256=<hex>`` header — an HMAC-SHA256 of the
exact request body. The receiver can recompute the HMAC with the shared secret
(see :func:`verify_signature`) to confirm the request really came from PokéTrack
and wasn't tampered with.

All network errors are caught and returned as ``(False, reason)`` — a bad
webhook never disrupts a refresh.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import requests

from .http import SESSION

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-PokeTrack-Signature"


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

    return {"content": message, "text": text, "title": title, "events": events[:25]}, provider


def sign(secret: str, body: bytes) -> str:
    """Compute the ``sha256=<hex>`` HMAC signature for a request body."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Constant-time check that ``signature`` matches the HMAC of ``body``.

    Provided for receivers (and tests) to validate incoming PokéTrack webhooks.
    """
    if not secret or not signature:
        return False
    expected = sign(secret, body)
    return hmac.compare_digest(expected, signature)


def send(
    url: str,
    title: str,
    message: str,
    events: list[dict],
    secret: Optional[str] = None,
    timeout: int = 10,
) -> tuple[bool, str]:
    """POST the alert (HMAC-signed if ``secret`` set). Returns ``(ok, detail)``."""
    if not url:
        return False, "no url configured"
    payload, provider = build_payload(url, title, message, events)
    # Serialise once so the signed bytes are exactly the bytes we send.
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers[SIGNATURE_HEADER] = sign(secret, body)
    try:
        resp = SESSION.post(url, data=body, headers=headers, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning("Webhook POST returned %s", resp.status_code)
        return ok, f"{provider}:{resp.status_code}"
    except requests.RequestException as exc:
        logger.warning("Webhook POST failed: %s", exc)
        return False, str(exc)
