from urllib.parse import urlencode

import pytest

from astra_shared.vk_launch_params import VkLaunchParamsError, compute_sign, validate_and_parse_launch_params

# Параметры и ключ — из примера dev.vk.com/ru/mini-apps/development/launch-params-sign;
# sign посчитан эталонной функцией is_valid оттуда же (sign в самом примере не сходится с ней).
VK_DOCS_SECRET = "wvl68m4dR1UpLrVRli"
VK_DOCS_LAUNCH_PARAMS = (
    "vk_user_id=494075&vk_app_id=6736218&vk_is_app_user=1&vk_are_notifications_enabled=1"
    "&vk_language=ru&vk_access_token_settings=&vk_platform=android"
    "&sign=htQFduJpLxz7ribXRZpDFUH-XEUhC9rBPTJkjUFEkRA"
)


def test_vk_docs_example_is_valid():
    result = validate_and_parse_launch_params(VK_DOCS_LAUNCH_PARAMS, VK_DOCS_SECRET)

    assert result["vk_user_id"] == "494075"
    assert result["vk_access_token_settings"] == ""
    assert "sign" not in result


def test_leading_question_mark_and_non_vk_params_ignored():
    result = validate_and_parse_launch_params(f"?{VK_DOCS_LAUNCH_PARAMS}&utm_source=x", VK_DOCS_SECRET)

    assert result["vk_app_id"] == "6736218"
    assert "utm_source" not in result


def test_wrong_secret_rejected():
    with pytest.raises(VkLaunchParamsError):
        validate_and_parse_launch_params(VK_DOCS_LAUNCH_PARAMS, "other-secret")


def test_tampered_user_id_rejected():
    tampered = VK_DOCS_LAUNCH_PARAMS.replace("vk_user_id=494075", "vk_user_id=1")
    with pytest.raises(VkLaunchParamsError):
        validate_and_parse_launch_params(tampered, VK_DOCS_SECRET)


def test_missing_sign_rejected():
    with pytest.raises(VkLaunchParamsError):
        validate_and_parse_launch_params("vk_user_id=494075&vk_app_id=6736218", VK_DOCS_SECRET)


def test_missing_user_id_rejected():
    params = {"vk_app_id": "6736218", "vk_platform": "android"}
    launch_params = urlencode({**params, "sign": compute_sign(params, VK_DOCS_SECRET)})
    with pytest.raises(VkLaunchParamsError):
        validate_and_parse_launch_params(launch_params, VK_DOCS_SECRET)


def test_malformed_launch_params_rejected():
    with pytest.raises(VkLaunchParamsError):
        validate_and_parse_launch_params("not-a-query-string", VK_DOCS_SECRET)
