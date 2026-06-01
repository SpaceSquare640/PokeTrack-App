"""Optional Telegram notification channel.

Uses the Telegram Bot API ``sendMessage`` endpoint via the shared HTTP session.
Configure ``telegram_bot_token`` + ``telegram_chat_id`` to enable. Like the
webhook, all errors are swallowed and returned as ``(False, reason)`` so a
misconfiguration never disrupts a refresh.
"""
from __future__ import annotations

import logging

import requests

from .http import SESSION

logger = logging.getLogger(__name__)


def send(token: str, chat_id: str, text: str, timeout: int = 10) -> tuple[bool, str]:
    """POST a message to a Telegram chat. Returns ``(ok, detail)``."""
    if not token or not chat_id:
        return False, "not configured"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = SESSION.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=timeout,
        )
        ok = 200 <= resp.status_code < 300
        if not ok:
            logger.warning("Telegram sendMessage returned %s", resp.status_code)
        return ok, str(resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False, str(exc)
