"""
Детерминированный слой натальной карты: из долгот тел и куспидов собирает
снимок карты (знаки, дома, аспекты, конфигурации, доминанты). LLM здесь нет —
расшифровка опирается на эти готовые числа и не считает их сама.

Снимок — dict с snake_case-ключами, совпадающими с полями схем API astra-app;
он же сохраняется в natal_charts.chart.
"""

import itertools
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from astra_shared.astro.ephemeris import PLANETS as EPHEMERIS_PLANETS
from astra_shared.astro.ephemeris import Ephemeris
from astra_shared.astro.natal import (
    build_natal_chart,
    mean_lilith_longitude,
    mean_lunar_node_longitude,
)
from astra_shared.astro.natal_reference import (
    ANGULAR_HOUSES,
    ASPECTS,
    CLASSIC_PLANETS,
    ELEMENT_COLORS,
    ELEMENT_NAMES,
    EXACTNESS_ORB_SCALE,
    HOUSE_AREAS,
    LUMINARY_ORB_BONUS,
    MODALITY_NAMES,
    PLANETS,
    SIGNS,
    NatalChartHouseSystem,
    NatalChartPlanetKey,
)

ENGINE_VERSION = 1
DEFAULT_BIRTH_TIME = time(hour=12)

_P = NatalChartPlanetKey
_MEAN_POINT_SPEED_STEP_DAYS = 0.5


@dataclass(frozen=True)
class BirthData:
    birth_date: date
    birth_time: time
    lat: float
    lng: float
    timezone: str

    @property
    def local_datetime(self) -> datetime:
        return datetime.combine(self.birth_date, self.birth_time, tzinfo=ZoneInfo(self.timezone))

    @property
    def utc_datetime(self) -> datetime:
        return self.local_datetime.astimezone(UTC)


def utc_offset_label(moment: datetime) -> str:
    offset = moment.utcoffset()
    total_minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


@dataclass(frozen=True)
class RawChart:
    longitudes: dict[NatalChartPlanetKey, float]
    speeds: dict[NatalChartPlanetKey, float]
    cusps: list[float]
    ascendant: float
    midheaven: float
    house_system: NatalChartHouseSystem


def _mean_point_speed(longitude_at, jd_tt: float) -> float:
    step = _MEAN_POINT_SPEED_STEP_DAYS
    delta = (longitude_at(jd_tt + step) - longitude_at(jd_tt - step) + 180) % 360 - 180
    return delta / (2 * step)


def calculate_raw_chart(ephemeris: Ephemeris, birth: BirthData) -> RawChart:
    chart = build_natal_chart(
        ephemeris, birth.birth_date, birth.birth_time, birth.lat, birth.lng, birth.timezone
    )
    t = ephemeris.t(birth.utc_datetime)
    jd_tt = float(t.tt)

    longitudes = {_P(body): float(chart.longitudes[body]) for body in EPHEMERIS_PLANETS}
    speeds = {_P(body): float(ephemeris.speed(body, t)) for body in EPHEMERIS_PLANETS}
    longitudes[_P.NORTH_NODE] = mean_lunar_node_longitude(jd_tt)
    speeds[_P.NORTH_NODE] = _mean_point_speed(mean_lunar_node_longitude, jd_tt)
    longitudes[_P.LILITH] = mean_lilith_longitude(jd_tt)
    speeds[_P.LILITH] = _mean_point_speed(mean_lilith_longitude, jd_tt)

    return RawChart(
        longitudes=longitudes,
        speeds=speeds,
        cusps=[float(cusp) for cusp in chart.cusps],
        ascendant=float(chart.longitudes["asc"]),
        midheaven=float(chart.longitudes["mc"]),
        house_system=NatalChartHouseSystem(chart.house_system),
    )


def sign_index(longitude: float) -> int:
    return int(longitude % 360 // 30) % 12


def degree_in_sign(longitude: float) -> float:
    return longitude % 360 % 30


def format_position(longitude: float) -> str:
    degree = degree_in_sign(longitude)
    whole = int(degree)
    minutes = round((degree - whole) * 60)
    if minutes == 60:
        whole, minutes = whole + 1, 0
    return f"{whole}°{minutes:02d}' {SIGNS[sign_index(longitude)].name}"


def angular_separation(a: float, b: float) -> float:
    delta = abs(a % 360 - b % 360) % 360
    return 360 - delta if delta > 180 else delta


def house_of(longitude: float, cusps: list[float]) -> int:
    longitude %= 360
    for i in range(12):
        start = cusps[i]
        span = (cusps[(i + 1) % 12] - start) % 360
        if (longitude - start) % 360 < span:
            return i + 1
    return 12


def _sign_fields(longitude: float) -> dict:
    sign = SIGNS[sign_index(longitude)]
    return {
        "sign": sign.name,
        "sign_glyph": sign.glyph,
        "degree": round(degree_in_sign(longitude), 2),
        "position": format_position(longitude),
    }


def _planets(raw: RawChart) -> list[dict]:
    planets = []
    for key, info in PLANETS.items():
        longitude = raw.longitudes[key]
        planets.append(
            {
                "key": key.value,
                "name": info.name,
                "glyph": info.glyph,
                **_sign_fields(longitude),
                "house": house_of(longitude, raw.cusps),
                "retrograde": raw.speeds[key] < 0,
                "lon": round(longitude % 360, 4),
            }
        )
    return planets


def _aspects(raw: RawChart) -> list[dict]:
    aspects = []
    for a, b in itertools.combinations(PLANETS, 2):
        separation = angular_separation(raw.longitudes[a], raw.longitudes[b])
        bonus = LUMINARY_ORB_BONUS if PLANETS[a].is_luminary or PLANETS[b].is_luminary else 0.0
        for aspect in ASPECTS:
            orb = abs(separation - aspect.angle)
            if orb <= aspect.orb + bonus:
                aspects.append(
                    {
                        "a": a.value,
                        "b": b.value,
                        "a_name": PLANETS[a].name,
                        "b_name": PLANETS[b].name,
                        "type": aspect.type.value,
                        "name": aspect.name,
                        "glyph": aspect.glyph,
                        "angle": aspect.angle,
                        "orb": round(orb, 2),
                        "exactness": round(max(0.0, 1 - orb / EXACTNESS_ORB_SCALE), 3),
                        "harmony": aspect.harmony.value,
                    }
                )
                break
    return sorted(aspects, key=lambda item: item["orb"])


def _has_aspect(aspects: list[dict], aspect_type: str, a: str, b: str) -> bool:
    return any(item["type"] == aspect_type and {item["a"], item["b"]} == {a, b} for item in aspects)


def _patterns(raw: RawChart, aspects: list[dict]) -> list[dict]:
    patterns: list[dict] = []
    classic = [key.value for key in CLASSIC_PLANETS]

    by_sign: dict[int, list[str]] = {}
    for key in CLASSIC_PLANETS:
        by_sign.setdefault(sign_index(raw.longitudes[key]), []).append(key.value)
    for index, members in sorted(by_sign.items()):
        if len(members) >= 3:
            patterns.append({"type": "stellium", "name": "Стеллиум", "sign": SIGNS[index].name, "planets": members})

    for a, b, c in itertools.combinations(classic, 3):
        if all(_has_aspect(aspects, "trine", x, y) for x, y in ((a, b), (b, c), (a, c))):
            element = SIGNS[sign_index(raw.longitudes[NatalChartPlanetKey(a)])].element
            patterns.append(
                {"type": "grand_trine", "name": "Большой тригон", "element": element.value, "planets": [a, b, c]}
            )

    for item in aspects:
        if item["type"] != "opposition" or item["a"] not in classic or item["b"] not in classic:
            continue
        for apex in classic:
            if apex in (item["a"], item["b"]):
                continue
            if _has_aspect(aspects, "square", item["a"], apex) and _has_aspect(aspects, "square", item["b"], apex):
                patterns.append(
                    {"type": "t_square", "name": "Тау-квадрат", "opposition": [item["a"], item["b"]], "apex": apex}
                )
    return patterns


def _ruler(raw: RawChart, longitude: float) -> dict:
    sign = SIGNS[sign_index(longitude)]
    ruler_longitude = raw.longitudes[sign.ruler]
    return {
        "sign": sign.name,
        "ruler": PLANETS[sign.ruler].name,
        "placement": format_position(ruler_longitude),
        "house": house_of(ruler_longitude, raw.cusps),
    }


def _dominants(raw: RawChart) -> dict:
    elements = {element: 0 for element in ELEMENT_NAMES}
    modalities = {modality: 0 for modality in MODALITY_NAMES}
    for key in CLASSIC_PLANETS:
        sign = SIGNS[sign_index(raw.longitudes[key])]
        elements[sign.element] += 1
        modalities[sign.modality] += 1
    total = len(CLASSIC_PLANETS)

    cusp_signs = {sign_index(cusp) for cusp in raw.cusps}
    intercepted = [
        {"sign": SIGNS[index].name, "house": house_of(index * 30 + 15, raw.cusps)}
        for index in range(12)
        if index not in cusp_signs
    ]
    return {
        "elements": [
            {
                "key": element.value,
                "name": ELEMENT_NAMES[element],
                "count": count,
                "percent": round(count / total * 100),
                "color": ELEMENT_COLORS[element],
            }
            for element, count in elements.items()
        ],
        "modalities": [
            {"key": modality.value, "name": MODALITY_NAMES[modality], "count": count, "percent": round(count / total * 100)}
            for modality, count in modalities.items()
        ],
        "chart_ruler": _ruler(raw, raw.ascendant),
        "intercepted_signs": intercepted,
    }


def _houses(raw: RawChart, planets: list[dict]) -> list[dict]:
    houses = []
    for i, cusp in enumerate(raw.cusps):
        number = i + 1
        sign = SIGNS[sign_index(cusp)]
        houses.append(
            {
                "number": number,
                "area": HOUSE_AREAS[number],
                "cusp_sign": sign.name,
                "cusp_sign_glyph": sign.glyph,
                "cusp_degree": round(degree_in_sign(cusp), 2),
                "cusp_position": format_position(cusp),
                "cusp_lon": round(cusp % 360, 4),
                "ruler": _ruler(raw, cusp),
                "is_angular": number in ANGULAR_HOUSES,
                "planets": [
                    {
                        "key": planet["key"],
                        "name": planet["name"],
                        "glyph": planet["glyph"],
                        "degree": planet["degree"],
                        "retrograde": planet["retrograde"],
                    }
                    for planet in planets
                    if planet["house"] == number
                ],
            }
        )
    return houses


def _hemispheres(planets: list[dict]) -> dict:
    classic = [planet for planet in planets if planet["key"] in {key.value for key in CLASSIC_PLANETS}]
    return {
        "upper": sum(1 for planet in classic if 7 <= planet["house"] <= 12),
        "lower": sum(1 for planet in classic if 1 <= planet["house"] <= 6),
        "east": sum(1 for planet in classic if planet["house"] in (10, 11, 12, 1, 2, 3)),
        "west": sum(1 for planet in classic if planet["house"] in (4, 5, 6, 7, 8, 9)),
    }


def _big_three(raw: RawChart, planets: list[dict]) -> dict:
    by_key = {planet["key"]: planet for planet in planets}

    def luminary(key: NatalChartPlanetKey) -> dict:
        planet = by_key[key.value]
        return {
            "label": planet["name"],
            "glyph": planet["glyph"],
            "sign": planet["sign"],
            "sign_glyph": planet["sign_glyph"],
            "degree": planet["degree"],
            "position": planet["position"],
            "house": planet["house"],
        }

    def axis(label: str, glyph: str, longitude: float) -> dict:
        return {"label": label, "glyph": glyph, **_sign_fields(longitude), "lon": round(longitude % 360, 4)}

    return {
        "sun": luminary(NatalChartPlanetKey.SUN),
        "moon": luminary(NatalChartPlanetKey.MOON),
        "ascendant": axis("Асцендент", "Asc", raw.ascendant),
        "midheaven": axis("MC", "MC", raw.midheaven),
    }


def build_chart_snapshot(raw: RawChart, birth_utc: datetime, utc_offset_label: str) -> dict:
    planets = _planets(raw)
    aspects = _aspects(raw)
    return {
        "datetime_utc": birth_utc.isoformat(),
        "utc_offset_label": utc_offset_label,
        "house_system": raw.house_system.value,
        "big_three": _big_three(raw, planets),
        "dominants": _dominants(raw),
        "hemispheres": _hemispheres(planets),
        "planets": planets,
        "houses": _houses(raw, planets),
        "aspects": aspects,
        "patterns": _patterns(raw, aspects),
    }


def calculate_chart_snapshot(ephemeris: Ephemeris, birth: BirthData) -> dict:
    return build_chart_snapshot(
        calculate_raw_chart(ephemeris, birth), birth.utc_datetime, utc_offset_label(birth.local_datetime)
    )
