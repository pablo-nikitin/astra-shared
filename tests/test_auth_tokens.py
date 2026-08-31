import pytest

from astra_shared.auth_tokens import AccessTokenError, create_access_token, decode_access_token


def test_roundtrip():
    token, ttl = create_access_token("secret", "user-1", "telegram", "42", 3600)
    payload = decode_access_token("secret", token)
    assert payload.user_uuid == "user-1"
    assert payload.provider == "telegram"
    assert payload.external_id == "42"
    assert ttl == 3600


def test_external_id_is_stringified():
    token, _ = create_access_token("secret", "user-1", "telegram", 42, 3600)
    payload = decode_access_token("secret", token)
    assert payload.external_id == "42"


def test_wrong_secret_rejected():
    token, _ = create_access_token("secret", "user-1", "telegram", "42", 3600)
    with pytest.raises(AccessTokenError):
        decode_access_token("other-secret", token)


def test_expired_token_rejected():
    token, _ = create_access_token("secret", "user-1", "telegram", "42", -1)
    with pytest.raises(AccessTokenError):
        decode_access_token("secret", token)


def test_malformed_token_rejected():
    with pytest.raises(AccessTokenError):
        decode_access_token("secret", "not-a-valid-token")


def test_tampered_payload_rejected():
    token, _ = create_access_token("secret", "user-1", "telegram", "42", 3600)
    payload_b64, signature = token.split(".", 1)
    with pytest.raises(AccessTokenError):
        decode_access_token("secret", f"{payload_b64}x.{signature}")
