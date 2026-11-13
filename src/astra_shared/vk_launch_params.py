import base64
import hashlib
import hmac
from urllib.parse import parse_qsl, urlencode


class VkLaunchParamsError(Exception):
    pass


def compute_sign(vk_params: dict[str, str], app_secret: str) -> str:
    query = urlencode(sorted(vk_params.items()), doseq=True)
    digest = hmac.new(app_secret.encode(), query.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def validate_and_parse_launch_params(launch_params: str, app_secret: str) -> dict:
    try:
        data = dict(parse_qsl(launch_params.lstrip("?"), keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise VkLaunchParamsError("malformed launch params") from exc

    received_sign = data.get("sign")
    if not received_sign:
        raise VkLaunchParamsError("missing sign")

    vk_params = {key: value for key, value in data.items() if key.startswith("vk_")}
    if not hmac.compare_digest(received_sign, compute_sign(vk_params, app_secret)):
        raise VkLaunchParamsError("signature mismatch")

    if not vk_params.get("vk_user_id"):
        raise VkLaunchParamsError("missing vk_user_id")

    return vk_params
