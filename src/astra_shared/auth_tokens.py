import base64
import hashlib
import hmac
import json
import time

from astra_shared.identity_contract import AccessTokenPayload


class AccessTokenError(Exception):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(secret: str, payload_b64: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64url_encode(digest[:16])


def create_access_token(
    secret: str, user_uuid: str, provider: str, external_id: str, ttl_seconds: int
) -> tuple[str, int]:
    payload = {
        "sub": user_uuid,
        "provider": provider,
        "external_id": str(external_id),
        "exp": int(time.time()) + ttl_seconds,
        "v": 1,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(secret, payload_b64)}", ttl_seconds


def decode_access_token(secret: str, token: str) -> AccessTokenPayload:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        raise AccessTokenError("malformed token") from None

    if not hmac.compare_digest(signature, _sign(secret, payload_b64)):
        raise AccessTokenError("invalid signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AccessTokenError("malformed payload") from exc

    if payload.get("exp", 0) < time.time():
        raise AccessTokenError("token expired")

    return AccessTokenPayload(
        user_uuid=payload["sub"],
        provider=payload["provider"],
        external_id=payload["external_id"],
    )
