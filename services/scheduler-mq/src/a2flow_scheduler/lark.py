"""Feishu (Lark) incoming-webhook delivery client.

Secrets live only in the process environment and are never echoed in errors,
logs, or exception messages. Delivery is bounded (timeout, max attempts) and
the caller owns deduplication.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Callable


class LarkWebhookError(Exception):
    """Delivery failed after all attempts."""


class LarkWebhookClient:
    def __init__(
        self,
        webhook_url: str,
        *,
        secret: str | None = None,
        timeout: float = 8.0,
        max_attempts: int = 3,
        opener_factory: Callable[[], object] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(webhook_url, str) or not webhook_url.startswith(
            "https://open.feishu.cn"
        ):
            raise ValueError("INVALID_LARK_WEBHOOK_URL")
        if secret is not None and not secret:
            raise ValueError("EMPTY_LARK_SECRET")
        self._url = webhook_url
        self._secret = secret
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        self._opener_factory = opener_factory or urllib.request.build_opener
        self._sleep = sleep or time.sleep

    def sign(self, timestamp_seconds: int) -> str:
        """HMAC-SHA256 over `timestamp\nsecret`, base64 (Feishu sign mode)."""
        if self._secret is None:
            raise ValueError("LARK_SECRET_NOT_CONFIGURED")
        message = f"{timestamp_seconds}\n{self._secret}".encode("utf-8")
        digest = hmac.new(message, digestmod=hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def send(self, card: dict, *, dedup_key: str | None = None) -> None:
        if not isinstance(card, dict):
            raise ValueError("INVALID_LARK_CARD")
        body = json.dumps(
            {"msg_type": "interactive", "card": card},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        last_error = "NO_ATTEMPT"
        for attempt in range(1, self._max_attempts + 1):
            timestamp = int(time.time())
            request = urllib.request.Request(
                self._url, data=body, method="POST"
            )
            request.add_header("Content-Type", "application/json")
            if self._secret is not None:
                request.add_header("X-Lark-Signature", self.sign(timestamp))
                request.add_header("X-Lark-Request-Timestamp", str(timestamp))
            try:
                with self._opener_factory().open(
                    request, timeout=self._timeout
                ) as response:
                    status = getattr(response, "status", None) or response.code
                    payload = json.loads(response.read().decode("utf-8"))
                if 200 <= status < 300 and self._accepted(payload):
                    return
                last_error = "LARK_REJECTED"
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_error = "LARK_TRANSPORT"
                if attempt == self._max_attempts:
                    raise LarkWebhookError(last_error) from exc
            self._sleep(min(2 ** (attempt - 1), 8))
        raise LarkWebhookError(last_error)

    @staticmethod
    def _accepted(payload: dict) -> bool:
        code = payload.get("code")
        if code is None:
            code = payload.get("StatusCode")
        return code in (0, "0")
