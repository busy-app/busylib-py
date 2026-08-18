from __future__ import annotations

import httpx2
import pytest

from busylib import AsyncBusyBar, BusyBar, types

TOKEN_PAYLOAD = {
    "short_id": "ab12",
    "display_id": "ab12-cdef",
    "name": "laptop",
    "created_at": 1785515110,
    "last_used_at": 1785515200,
    "token": "secret-value",
}


def _client(responder) -> BusyBar:
    return BusyBar(
        addr="http://device.local", transport=httpx2.MockTransport(responder)
    )


def _async_client(responder) -> AsyncBusyBar:
    return AsyncBusyBar(
        addr="http://device.local", transport=httpx2.MockTransport(responder)
    )


def test_tokens_list_parses_the_collection() -> None:
    """
    A token listing comes back as models, not raw dicts.
    """
    seen: dict[str, str] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        return httpx2.Response(200, json={"tokens": [TOKEN_PAYLOAD]})

    info = _client(responder).access_tokens_list()

    assert seen == {"path": "/api/access/tokens", "method": "GET"}
    assert isinstance(info, types.AccessTokensInfo)
    assert info.tokens[0].short_id == "ab12"


def test_token_mint_sends_the_name_and_returns_the_secret() -> None:
    """
    Minting posts the requested name and yields the one-time secret.
    """
    seen: dict[str, object] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx2.Response(200, json=TOKEN_PAYLOAD)

    token = _client(responder).access_token_mint("laptop")

    assert seen["path"] == "/api/access/tokens"
    assert b"laptop" in bytes(seen["body"])  # type: ignore[arg-type]
    assert token.token == "secret-value"


def test_token_without_a_secret_parses() -> None:
    """
    Listing omits the secret, so the field has to stay optional.

    The device returns it only when the token is minted.
    """
    payload = {k: v for k, v in TOKEN_PAYLOAD.items() if k != "token"}

    def responder(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"tokens": [payload]})

    info = _client(responder).access_tokens_list()

    assert info.tokens[0].token is None


def test_tokens_delete_all_uses_delete_on_the_collection() -> None:
    """
    Revoking everything is a DELETE on the collection.
    """
    seen: dict[str, str] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        return httpx2.Response(200, json={"result": "OK"})

    assert _client(responder).access_tokens_delete_all().result == "OK"
    assert seen == {"path": "/api/access/tokens", "method": "DELETE"}


def test_tokens_revoke_addresses_a_single_token() -> None:
    """
    Revoking one token puts its short id in the path.
    """
    seen: dict[str, str] = {}

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        return httpx2.Response(200, json={"result": "OK"})

    _client(responder).access_tokens_revoke("ab12")

    assert seen == {"path": "/api/access/tokens/ab12", "method": "DELETE"}


@pytest.mark.asyncio
async def test_async_token_helpers_hit_the_same_endpoints() -> None:
    """
    The async client mirrors the sync one, path for path.
    """
    seen: list[tuple[str, str]] = []

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx2.Response(200, json={"tokens": []})
        if request.method == "POST":
            return httpx2.Response(200, json=TOKEN_PAYLOAD)
        return httpx2.Response(200, json={"result": "OK"})

    client = _async_client(responder)
    await client.access_tokens_list()
    await client.access_token_mint("laptop")
    await client.access_tokens_revoke("ab12")
    await client.access_tokens_delete_all()
    await client.aclose()

    assert seen == [
        ("GET", "/api/access/tokens"),
        ("POST", "/api/access/tokens"),
        ("DELETE", "/api/access/tokens/ab12"),
        ("DELETE", "/api/access/tokens"),
    ]
