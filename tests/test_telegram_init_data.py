import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from astra_shared.telegram_init_data import TelegramInitDataError, validate_and_parse_init_data


def _build_init_data(bot_token: str, fields: dict) -> str:
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": computed_hash})


def test_valid_init_data_parsed():
    fields = {"auth_date": "1700000000", "user": json.dumps({"id": 123, "first_name": "A"})}
    init_data = _build_init_data("BOT:TOKEN", fields)

    result = validate_and_parse_init_data(init_data, "BOT:TOKEN")

    assert result["auth_date"] == "1700000000"
    assert result["user"] == {"id": 123, "first_name": "A"}
    assert result["telegram_user_id"] == "123"
    assert "hash" not in result


def test_wrong_bot_token_rejected():
    init_data = _build_init_data("BOT:TOKEN", {"auth_date": "1700000000"})
    with pytest.raises(TelegramInitDataError):
        validate_and_parse_init_data(init_data, "OTHER:TOKEN")


def test_missing_hash_rejected():
    with pytest.raises(TelegramInitDataError):
        validate_and_parse_init_data("auth_date=1700000000", "BOT:TOKEN")


def test_malformed_init_data_rejected():
    with pytest.raises(TelegramInitDataError):
        validate_and_parse_init_data("not-a-query-string", "BOT:TOKEN")


def test_unparsable_user_field_kept_as_string():
    fields = {"user": "not-json"}
    init_data = _build_init_data("BOT:TOKEN", fields)

    result = validate_and_parse_init_data(init_data, "BOT:TOKEN")

    assert result["user"] == "not-json"
    assert "telegram_user_id" not in result
