"""Explicit one-shot Telegram delivery; no automated trading or implicit network calls.

Sender requires explicit one-time user invocation and environment-only secrets.
This module is not used automatically by research, agents or replay.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def send_preview(message: str, *, confirmed: bool, env: dict | None = None) -> dict:
    if not confirmed:
        raise PermissionError("Explicit confirmation required before a network send")
    env = os.environ if env is None else env
    token = env.get("QUANTLAB_TELEGRAM_BOT_TOKEN", "")
    chat = env.get("QUANTLAB_TELEGRAM_CHAT_ID", "")
    allow = {x.strip() for x in env.get("QUANTLAB_TELEGRAM_ALLOWED_CHATS", "").split(",") if x.strip()}
    if not token or not chat or chat not in allow:
        raise PermissionError("Missing bot/chat credentials or chat is not allowlisted")
    if not message.startswith("[Agent Quant Lab | simulation/research]") or len(message) > 3500:
        raise ValueError("Only bounded sanitised research message previews can be sent")
    data = urlencode({"chat_id": chat, "text": message, "disable_web_page_preview": "true"}).encode()
    # Fixed endpoint, token never logged or included in exception text by caller.
    req = Request("https://api.telegram.org/bot" + token + "/sendMessage", data=data,
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read(10000))
            if not payload.get("ok"):
                raise RuntimeError("Telegram rejected message")
    except Exception as exc:
        # urllib may include the credential-bearing URL in its error details.
        raise RuntimeError("Telegram delivery failed (redacted)") from None
    return {"sent": True, "chat": chat, "message_id": payload.get("result", {}).get("message_id")}
