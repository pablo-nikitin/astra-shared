import asyncio
import base64
import json

import httpx
import pytest

from astra_shared.payments.yookassa import create_payment, get_payment_status


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.yookassa.ru/v3")


def test_create_payment_sends_expected_request():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotence-Key"] == "idem-1"
        expected_auth = base64.b64encode(b"shop-1:secret-1").decode()
        assert request.headers["Authorization"] == f"Basic {expected_auth}"
        body = json.loads(request.content)
        assert body["amount"] == {"value": "990.00", "currency": "RUB"}
        assert body["confirmation"] == {"type": "redirect", "return_url": "https://return"}
        assert body["metadata"] == {"user_uuid": "u1"}
        return httpx.Response(200, json={"id": "pay_1", "confirmation": {"confirmation_url": "https://pay/1"}})

    async def run():
        async with _client(handler) as client:
            return await create_payment(
                client,
                shop_id="shop-1",
                secret_key="secret-1",
                idempotence_key="idem-1",
                amount_rub=990,
                description="desc",
                return_url="https://return",
                metadata={"user_uuid": "u1"},
            )

    result = asyncio.run(run())
    assert result["id"] == "pay_1"


def test_get_payment_status_returns_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/payments/pay_1"
        return httpx.Response(200, json={"status": "succeeded"})

    async def run():
        async with _client(handler) as client:
            return await get_payment_status(client, shop_id="shop-1", secret_key="secret-1", payment_id="pay_1")

    assert asyncio.run(run()) == "succeeded"


def test_non_2xx_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad_request"})

    async def run():
        async with _client(handler) as client:
            await create_payment(
                client,
                shop_id="shop-1",
                secret_key="secret-1",
                idempotence_key="idem-1",
                amount_rub=1,
                description="desc",
                return_url="https://return",
                metadata={},
            )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
