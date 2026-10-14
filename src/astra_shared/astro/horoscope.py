"""
Ежедневный гороскоп по натальной карте: транзиты планет к натальным точкам.

Берём положение планет на местный полдень, ищем мажорные аспекты к натальным
Солнцу–Сатурну, ASC и MC в пределах орбиса, взвешиваем по значимости планет
и точности аспекта. Сильнейшие транзиты дают заголовок и текст дня,
по сферам (любовь, работа, деньги, самочувствие) — свой транзит и оценку 1–5.

`daily_horoscope` — структура на ключах, `present_horoscope` — она же с
текстами из `horoscope_texts`. Открытие полного дня оплачивается записью
ledger с ключом HOROSCOPE_DAY_UNLOCK_* — одной на бот и мини-апп.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astra_shared.astro import horoscope_texts as hx
from astra_shared.astro.ephemeris import PLANETS, Ephemeris, sign_of
from astra_shared.astro.natal import NatalChart

HOROSCOPE_DAY_UNLOCK_PRICE = 1
HOROSCOPE_DAY_UNLOCK_REASON = "horoscope_day_unlock"
HOROSCOPE_DAY_UNLOCK_REFERENCE = "horoscope_day"
HOROSCOPE_DAY_UNLOCK_COMMENT = hx.UNLOCK_LEDGER_COMMENT
HOROSCOPE_CONTENT_VERSION = hx.CONTENT_VERSION

TRANSIT_BODIES = PLANETS
NATAL_TARGETS = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "asc", "mc")

ORBS = {
    "moon": 5.0, "sun": 3.0, "mercury": 3.0, "venus": 3.0, "mars": 3.0,
    "jupiter": 2.0, "saturn": 2.0, "uranus": 1.5, "neptune": 1.5, "pluto": 1.5,
}
# Гороскоп ежедневный: быстрые планеты меняют картину каждый день и весят больше,
# медленные (Юпитер–Плутон) держатся неделями и идут в «фон».
TRANSIT_WEIGHT = {
    "moon": 1.3, "sun": 1.1, "mercury": 1.0, "venus": 1.1, "mars": 1.2,
    "jupiter": 1.0, "saturn": 1.1, "uranus": 0.9, "neptune": 0.85, "pluto": 0.95,
}
SLOW_BODIES = {"jupiter", "saturn", "uranus", "neptune", "pluto"}
NATAL_WEIGHT = {
    "sun": 1.5, "moon": 1.4, "asc": 1.3, "mc": 1.1, "venus": 1.1,
    "mars": 1.0, "mercury": 0.9, "saturn": 0.8, "jupiter": 0.7,
}
ASPECT_ANGLES = {0: "conjunction", 60: "sextile", 90: "square", 120: "trine", 180: "opposition"}
NATURE = {"conjunction": "fusion", "sextile": "soft", "trine": "soft", "square": "hard", "opposition": "hard"}

# Сферы в порядке показа: какие планеты и дома за них отвечают, ключевая планета для фона.
SPHERES = {
    "love": {"planets": {"venus", "mars", "moon"}, "houses": {5, 7}, "key": "venus"},
    "work": {"planets": {"sun", "saturn", "mercury", "mc"}, "houses": {6, 10}, "key": "saturn"},
    "money": {"planets": {"jupiter", "venus", "saturn"}, "houses": {2, 8}, "key": "jupiter"},
    "health": {"planets": {"mars", "sun", "moon", "asc"}, "houses": {1, 6}, "key": "mars"},
}
FREE_SPHERE = "love"


@dataclass(frozen=True)
class Transit:
    body: str
    target: str
    aspect: str
    nature: str
    orb: float
    applying: bool
    score: float


def find_transits(ephemeris: Ephemeris, natal: NatalChart, moment: datetime) -> list[Transit]:
    t = ephemeris.t(moment)
    t_next = ephemeris.ts.tt_jd(t.tt + 0.25)
    transits: list[Transit] = []
    for body in TRANSIT_BODIES:
        lon = float(ephemeris.longitude(body, t))
        lon_next = float(ephemeris.longitude(body, t_next))
        for target in NATAL_TARGETS:
            if target not in natal.longitudes:
                continue
            natal_lon = natal.longitudes[target]
            diff = abs((lon - natal_lon + 180) % 360 - 180)
            diff_next = abs((lon_next - natal_lon + 180) % 360 - 180)
            for angle, aspect in ASPECT_ANGLES.items():
                orb = abs(diff - angle)
                if orb > ORBS[body]:
                    continue
                applying = abs(diff_next - angle) < orb
                exactness = 1 - orb / ORBS[body] * 0.6
                score = TRANSIT_WEIGHT[body] * NATAL_WEIGHT[target] * exactness * (1.1 if applying else 1.0)
                transits.append(Transit(body, target, aspect, NATURE[aspect], round(orb, 2), applying, round(score, 3)))
    return sorted(transits, key=lambda tr: tr.score, reverse=True)


def _mood(transits: list[Transit]) -> str:
    top = transits[:5]
    soft = sum(tr.score for tr in top if tr.nature == "soft")
    hard = sum(tr.score for tr in top if tr.nature == "hard")
    if not top:
        return "quiet"
    if soft and hard and min(soft, hard) / max(soft, hard) > 0.5:
        return "mixed"
    if hard > soft:
        return "hard"
    if soft > hard:
        return "soft"
    return "fusion"


def daily_horoscope(ephemeris: Ephemeris, natal: NatalChart, day: date, tz: str) -> dict:
    """Транзиты, сферы и оценки дня на ключах, без текстов. Момент — полдень дня в поясе tz."""
    noon = datetime.combine(day, time(12, 0), tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))
    transits = find_transits(ephemeris, natal, noon)
    # Не повторяем одну и ту же пару тел дважды (например, соединение и квадрат при широком орбисе).
    seen, unique = set(), []
    for tr in transits:
        if (tr.body, tr.target) not in seen:
            seen.add((tr.body, tr.target))
            unique.append(tr)
    transits = unique

    positions = {}
    t = ephemeris.t(noon)
    for body in TRANSIT_BODIES:
        lon = float(ephemeris.longitude(body, t))
        positions[body] = {"sign": sign_of(lon), "house": natal.house_of(lon)}

    spheres = {}
    used: set[tuple[str, str]] = set()
    for key, sphere in SPHERES.items():
        direct = [tr for tr in transits if tr.body in sphere["planets"] or tr.target in sphere["planets"]]
        by_house = [tr for tr in transits if positions[tr.body]["house"] in sphere["houses"] and tr not in direct]
        related = direct + by_house
        main = next((tr for tr in related if (tr.body, tr.target) not in used), None)
        if main:
            used.add((main.body, main.target))
        rating = 3.0
        for tr in related[:4]:
            delta = 0.6 * tr.score / 1.5
            rating += delta if tr.nature == "soft" else -delta if tr.nature == "hard" else delta / 2
        if positions["moon"]["house"] in sphere["houses"]:
            rating += 0.4
        spheres[key] = {
            "rating": max(1, min(5, round(rating))),
            "transit": _transit_dict(main) if main else None,
            "key_planet": {"body": sphere["key"], **positions[sphere["key"]]},
        }

    return {
        "date": day.isoformat(),
        "sun_sign": natal.sun_sign,
        "mood": _mood(transits),
        "moon_house": positions["moon"]["house"],
        "transits": [_transit_dict(tr) for tr in transits if tr.body not in SLOW_BODIES][:5],
        "background": [_transit_dict(tr) for tr in transits if tr.body in SLOW_BODIES][:3],
        "spheres": spheres,
        "positions": positions,
    }


def _transit_dict(tr: Transit) -> dict:
    return {
        "body": tr.body, "target": tr.target, "aspect": tr.aspect, "nature": tr.nature,
        "orb": tr.orb, "applying": tr.applying, "score": tr.score,
    }


def _transit_text(tr: dict) -> dict:
    target = hx.TARGETS[tr["target"]]
    phrase = hx.ASPECT_PHRASE[tr["aspect"]]
    obj = target["ins"] if tr["aspect"] == "conjunction" else target["dat"]
    # Атом — строка или {"text": ..., "caution": ...}; без атома — шаблон EFFECT.
    atom = hx.ATOMS.get(f"transit.{tr['body']}.{tr['aspect']}.{tr['target']}")
    if isinstance(atom, str):
        atom = {"text": atom}
    text = (atom or {}).get("text") or hx.EFFECT[tr["body"]][tr["nature"]].format(area=target["area"])
    return {
        **tr,
        "title": f"{hx.PLANET_NAMES[tr['body']]['name']} {phrase} {obj}",
        "glyph": (
            f"{hx.PLANET_NAMES[tr['body']]['glyph']} {hx.ASPECT_GLYPHS[tr['aspect']]} "
            f"{hx.PLANET_NAMES[tr['target']]['glyph']}"
        ),
        "text": text,
        "caution": (atom or {}).get("caution") or text,
    }


def present_horoscope(h: dict) -> dict:
    """День `daily_horoscope` с текстами: заголовок, абзацы, сферы, транзиты, фон, «чего опасаться»."""
    transits = [_transit_text(tr) for tr in h["transits"]]
    background = [_transit_text(tr) for tr in h["background"]]
    top = transits[0] if transits else (background[0] if background else None)
    if h["mood"] == "mixed":
        headline = hx.HEADLINE_MIXED
    elif top:
        headline = hx.HEADLINES[top["body"]][top["nature"]]
    else:
        headline = hx.HEADLINE_QUIET

    moon_house = h["moon_house"]
    body = [
        hx.MOON_HOUSE_INTRO.format(house=moon_house, house_theme=hx.HOUSE_THEMES[moon_house])
        + " "
        + hx.HOUSE_TEXTS[moon_house]
    ]
    body += [tr["text"] for tr in transits[:2]]

    spheres = []
    for key, sphere in h["spheres"].items():
        tr = _transit_text(sphere["transit"]) if sphere["transit"] else None
        kp = sphere["key_planet"]
        fallback = hx.SPHERE_FALLBACK[key].format(
            planet=hx.PLANET_NAMES[kp["body"]]["name"], in_sign=hx.SIGNS_IN[kp["sign"]],
            house=kp["house"], house_theme=hx.HOUSE_THEMES[kp["house"]],
        )
        spheres.append({
            "key": key, **hx.SPHERES[key], "rating": sphere["rating"],
            "title": tr["title"] if tr else f"{hx.PLANET_NAMES[kp['body']]['name']} {hx.SIGNS_IN[kp['sign']]}",
            "text": tr["text"] if tr else fallback,
        })

    hard = sorted((tr for tr in transits + background if tr["nature"] == "hard"), key=lambda tr: -tr["score"])
    return {
        "date": h["date"],
        "content_version": hx.CONTENT_VERSION,
        "sun_sign": h["sun_sign"],
        "mood": h["mood"],
        "headline": headline,
        "body": body,
        "spheres": spheres,
        "transits": transits,
        "background": background,
        "cautions": {
            "intro": hx.CAUTIONS_INTRO if hard else hx.CAUTIONS_EMPTY,
            "items": [{"title": tr["title"], "text": tr["caution"]} for tr in hard[:3]],
        },
    }
