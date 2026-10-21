import re
from functools import lru_cache

GENDER_FEMALE = "female"
GENDER_MALE = "male"
GENDER_UNKNOWN = "unknown"

_FIRST_WORD = re.compile(r"[А-Яа-яЁё]+")


@lru_cache(maxsize=1)
def _morph_analyzer():
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


def gender_from_name(name: str | None) -> str | None:
    """Пол по имени (pymorphy3); None — имя не распознано или общее («Саша»)."""
    match = _FIRST_WORD.match((name or "").strip())
    if not match:
        return None
    genders = {
        str(parse.tag.gender)
        for parse in _morph_analyzer().parse(match.group(0).lower())
        if "Name" in parse.tag and "nomn" in parse.tag
    }
    if genders == {"femn"}:
        return GENDER_FEMALE
    if genders == {"masc"}:
        return GENDER_MALE
    return None


def is_known_gender(value: str | None) -> bool:
    return value in (GENDER_FEMALE, GENDER_MALE)
