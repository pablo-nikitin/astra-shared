import hashlib
import hmac
import json
from urllib.parse import parse_qsl


class TelegramInitDataError(Exception):
    pass


def validate_and_parse_init_data(init_data: str, bot_token: str) -> dict:
    try:
        data = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise TelegramInitDataError("malformed init data") from exc
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataError("missing hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramInitDataError("signature mismatch")

    if "user" in data:
        try:
            data["user"] = json.loads(data["user"])
        except (ValueError, TypeError):
            pass
        else:
            data["telegram_user_id"] = str(data["user"].get("id", ""))

    return data
