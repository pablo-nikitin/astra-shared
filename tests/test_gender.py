import pytest

from astra_shared.gender import GENDER_FEMALE, GENDER_MALE, gender_from_name, is_known_gender


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Мария", GENDER_FEMALE),
        ("аня", GENDER_FEMALE),
        ("Иван", GENDER_MALE),
        ("  Дмитрий Петрович", GENDER_MALE),
        ("Саша", None),
        ("Женя", None),
        ("Maria", None),
        ("", None),
        (None, None),
    ],
)
def test_gender_from_name(name, expected):
    assert gender_from_name(name) == expected


def test_is_known_gender():
    assert is_known_gender("female") and is_known_gender("male")
    assert not is_known_gender("unknown") and not is_known_gender(None)
