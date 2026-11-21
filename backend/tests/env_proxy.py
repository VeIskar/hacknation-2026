"""Proxy ze zmiennych środowiskowych bez sieci: zapis, czy zapytanie poszło przez proxy.

httpx bierze proxy z env tylko bez własnego transportu (`allow_env_proxies = trust_env and
transport is None` w httpx 0.28), więc atrapa transportu tego nie sprawdzi. Tu dobór transportu
zostaje prawdziwy, a podmienione jest tylko wysłanie zapytania. Domyślny HTTPTransport powstaje
bez `proxy`, transport proxy z env dostaje `proxy=`.
"""

from typing import Any

import httpx
import pytest

PROXY_URL = "http://proxy.test:3128"


def record_proxy_use(monkeypatch: pytest.MonkeyPatch, reply_json: dict[str, Any]) -> list[str | None]:
    """Ustawia proxy w env. Dla każdego zapytania dopisuje adres proxy albo None, gdy poszło wprost."""
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, PROXY_URL)
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)

    used: list[str | None] = []
    original_init = httpx.HTTPTransport.__init__

    def init(self: httpx.HTTPTransport, *args: Any, proxy: Any = None, **kwargs: Any) -> None:
        original_init(self, *args, proxy=proxy, **kwargs)
        self.recorded_proxy = None if proxy is None else str(getattr(proxy, "url", proxy))

    def handle_request(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        used.append(self.recorded_proxy)
        return httpx.Response(200, json=reply_json)

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", init)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    return used
