import base64

import httpx

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"


def _auth_header(shop_id: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def create_payment(
    client: httpx.AsyncClient,
    *,
    shop_id: str,
    secret_key: str,
    idempotence_key: str,
    amount_rub: int,
    description: str,
    return_url: str,
    metadata: dict[str, str],
    receipt: dict | None = None,
) -> dict:
    payload = {
        "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description,
        "metadata": metadata,
    }
    if receipt is not None:
        payload["receipt"] = receipt

    response = await client.post(
        "/payments",
        headers={**_auth_header(shop_id, secret_key), "Idempotence-Key": idempotence_key},
        json=payload,
    )
    response.raise_for_status()
    return response.json()


async def get_payment_status(client: httpx.AsyncClient, *, shop_id: str, secret_key: str, payment_id: str) -> str:
    response = await client.get(f"/payments/{payment_id}", headers=_auth_header(shop_id, secret_key))
    response.raise_for_status()
    return response.json()["status"]
