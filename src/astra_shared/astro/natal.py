"""
Натальная карта: долготы планет на момент рождения, ASC/MC и дома.

Считаем долготы планет на момент рождения, ASC/MC и дома по Плациду.
За полярным кругом Плацид не определён — переходим на Порфирия.
Если время рождения неизвестно, домов нет: используем солярные дома
(1-й дом = знак Солнца, целые знаки) и помечаем карту как приблизительную.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from astra_shared.astro.ephemeris import PLANETS, Ephemeris, sign_of

PLACIDUS_MAX_LATITUDE = 66.0

# Точки натальной карты, к которым показываем аспекты транзитной Луны.
NATAL_POINTS_FOR_ASPECTS = ("sun", "moon", "mercury", "venus", "mars", "asc", "mc")


@dataclass
class NatalChart:
    longitudes: dict[str, float]  # планеты + asc/mc (если известно время)
    cusps: list[float]  # 12 куспидов, cusps[0] — 1-й дом
    house_system: str  # placidus | porphyry | solar
    birth_time_known: bool
    sun_sign: str = field(init=False)
    moon_sign: str = field(init=False)

    def __post_init__(self) -> None:
        self.sun_sign = sign_of(self.longitudes["sun"])
        self.moon_sign = sign_of(self.longitudes["moon"])

    def house_of(self, longitude: float) -> int:
        """Номер дома (1..12), в который попадает долгота."""
        lon = longitude % 360
        for i in range(12):
            start = self.cusps[i]
            end = self.cusps[(i + 1) % 12]
            span = (end - start) % 360
            if (lon - start) % 360 < span:
                return i + 1
        return 12

    def aspect_points(self) -> dict[str, float]:
        return {k: v for k, v in self.longitudes.items() if k in NATAL_POINTS_FOR_ASPECTS}


def build_natal_chart(
    ephemeris: Ephemeris,
    birth_date: date,
    birth_time: time | None,
    lat: float,
    lon: float,
    tz: str,
) -> NatalChart:
    known = birth_time is not None
    local = datetime.combine(birth_date, birth_time or time(12, 0), tzinfo=ZoneInfo(tz))
    moment = local.astimezone(ZoneInfo("UTC"))
    t = ephemeris.t(moment)
    longitudes = {body: float(ephemeris.longitude(body, t)) for body in PLANETS}

    if not known:
        # Без времени Луна может сместиться до ~7°, поэтому дома — солярные.
        sun_sign_start = longitudes["sun"] // 30 * 30
        cusps = [(sun_sign_start + 30 * i) % 360 for i in range(12)]
        return NatalChart(longitudes=longitudes, cusps=cusps, house_system="solar", birth_time_known=False)

    eps = _obliquity(t.tt)
    armc = (ephemeris.gast_degrees(moment) + lon) % 360
    asc = _ascendant(armc, eps, lat)
    mc = _midheaven(armc, eps)
    longitudes["asc"] = asc
    longitudes["mc"] = mc

    if abs(lat) < PLACIDUS_MAX_LATITUDE:
        cusps = _placidus_cusps(armc, eps, lat, asc, mc)
        system = "placidus"
    else:
        cusps = _porphyry_cusps(asc, mc)
        system = "porphyry"
    return NatalChart(longitudes=longitudes, cusps=cusps, house_system=system, birth_time_known=True)


def mean_lunar_node_longitude(jd_tt: float) -> float:
    """Средний северный лунный узел, градусы (Meeus, «Astronomical Algorithms», гл. 47)."""
    c = (jd_tt - 2451545.0) / 36525.0
    return (125.0445479 - 1934.1362891 * c + 0.0020754 * c**2 + c**3 / 467441 - c**4 / 60616000) % 360


def mean_lilith_longitude(jd_tt: float) -> float:
    """Чёрная Луна (Лилит) — средний апогей лунной орбиты, градусы (Meeus, гл. 47)."""
    c = (jd_tt - 2451545.0) / 36525.0
    perigee = 83.3532465 + 4069.0137287 * c - 0.0103200 * c**2 - c**3 / 80053 + c**4 / 18999000
    return (perigee + 180) % 360


# ---------- сферическая астрономия ----------


def _obliquity(jd_tt: float) -> float:
    """Средний наклон эклиптики, градусы (нутацией ~9″ пренебрегаем)."""
    centuries = (jd_tt - 2451545.0) / 36525.0
    return 23.4392911 - 0.0130042 * centuries


def _ascendant(armc: float, eps: float, lat: float) -> float:
    r, e, f = map(math.radians, (armc, eps, lat))
    asc = math.degrees(math.atan2(math.cos(r), -(math.sin(r) * math.cos(e) + math.tan(f) * math.sin(e))))
    return asc % 360


def _midheaven(armc: float, eps: float) -> float:
    r, e = math.radians(armc), math.radians(eps)
    return math.degrees(math.atan2(math.sin(r), math.cos(r) * math.cos(e))) % 360


def _ra_to_ecliptic(ra: float, eps: float) -> float:
    r, e = math.radians(ra), math.radians(eps)
    return math.degrees(math.atan2(math.sin(r), math.cos(r) * math.cos(e))) % 360


def _declination(longitude: float, eps: float) -> float:
    return math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(longitude))))


def _placidus_cusp(armc: float, eps: float, lat: float, fraction: float, above_horizon: bool) -> float:
    """Куспид Плацида: точка, прошедшая заданную долю своей полудуги.

    Над горизонтом (11, 12 дома) — доля дневной полудуги от MC,
    под горизонтом (2, 3 дома) — доля ночной полудуги до IC.
    """
    tan_lat = math.tan(math.radians(lat))
    ra = armc + (90 * fraction if above_horizon else 180 - 90 * fraction)
    longitude = _ra_to_ecliptic(ra, eps)
    for _ in range(50):
        decl = math.radians(_declination(longitude, eps))
        ad = math.degrees(math.asin(max(-1.0, min(1.0, tan_lat * math.tan(decl)))))
        if above_horizon:
            ra = armc + fraction * (90 + ad)
        else:
            ra = armc + 180 - fraction * (90 - ad)
        new_longitude = _ra_to_ecliptic(ra, eps)
        if abs((new_longitude - longitude + 180) % 360 - 180) < 1e-7:
            break
        longitude = new_longitude
    return new_longitude


def _placidus_cusps(armc: float, eps: float, lat: float, asc: float, mc: float) -> list[float]:
    c11 = _placidus_cusp(armc, eps, lat, 1 / 3, above_horizon=True)
    c12 = _placidus_cusp(armc, eps, lat, 2 / 3, above_horizon=True)
    c2 = _placidus_cusp(armc, eps, lat, 2 / 3, above_horizon=False)
    c3 = _placidus_cusp(armc, eps, lat, 1 / 3, above_horizon=False)
    first_half = [asc, c2, c3, (mc + 180) % 360]
    second_half = [(asc + 180) % 360, (c2 + 180) % 360, (c3 + 180) % 360, mc]
    # Порядок домов: 1,2,3,4(IC),5,6,7,8,9,10(MC),11,12
    c5, c6 = (c11 + 180) % 360, (c12 + 180) % 360
    return [
        first_half[0], first_half[1], first_half[2], first_half[3],
        c5, c6,
        second_half[0], second_half[1], second_half[2], second_half[3],
        c11, c12,
    ]


def _porphyry_cusps(asc: float, mc: float) -> list[float]:
    ic = (mc + 180) % 360
    dsc = (asc + 180) % 360
    q1 = (ic - asc) % 360  # 1 → 4
    q2 = (dsc - ic) % 360  # 4 → 7
    cusps = [asc, asc + q1 / 3, asc + 2 * q1 / 3, ic, ic + q2 / 3, ic + 2 * q2 / 3]
    cusps = [c % 360 for c in cusps]
    return cusps + [(c + 180) % 360 for c in cusps]
