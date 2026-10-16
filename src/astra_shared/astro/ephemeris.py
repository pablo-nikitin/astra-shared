"""
Положения светил для натальной карты и лунного календаря.

Все долготы — геоцентрические видимые эклиптические долготы на эпоху даты
(тропический зодиак). Время — UTC (aware datetime).

Эфемериды: JPL DE421 через Skyfield (MIT). Swiss Ephemeris не используем —
она под AGPL, что для сетевого сервиса обязывает открыть весь код.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from skyfield import almanac, eclipselib
from skyfield.api import Loader, wgs84
from skyfield.framelib import ecliptic_frame
from skyfield.searchlib import find_discrete

EPHEMERIS_FILE = "de421.bsp"  # 1900–2053, ~17 МБ

SIGNS = (
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
)

PLANETS = (
    "sun", "moon", "mercury", "venus", "mars",
    "jupiter", "saturn", "uranus", "neptune", "pluto",
)
_EPH_TARGETS = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars barycenter",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "pluto": "pluto barycenter",
}


# Мажорные (птолемеевы) аспекты: угол -> ключ. Углы > 180 — те же аспекты
# в убывающей половине цикла (например, 270 — квадрат).
ASPECTS = {
    0: "conjunction",
    60: "sextile",
    90: "square",
    120: "trine",
    180: "opposition",
    240: "trine",
    270: "square",
    300: "sextile",
}

# Солнечное затмение возможно, если в новолуние |широта Луны| меньше ~1.58°.
SOLAR_ECLIPSE_MAX_MOON_LATITUDE = 1.58
SUPERMOON_MAX_DISTANCE_KM = 360_000

LUNAR_ECLIPSE_KINDS = {0: "penumbral", 1: "partial", 2: "total"}


@dataclass(frozen=True)
class Lunation:
    """Главная фаза: new / first_quarter / full / last_quarter."""

    kind: str
    at: datetime
    longitude: float  # долгота Луны в момент фазы


@dataclass(frozen=True)
class Ingress:
    body: str
    at: datetime
    sign: str  # знак, в который вошло тело


@dataclass(frozen=True)
class AspectHit:
    """Точный аспект Луны к телу/точке."""

    target: str
    aspect: str
    angle: int
    at: datetime


@dataclass(frozen=True)
class Station:
    body: str
    at: datetime
    direction: str  # "retrograde" — разворот назад, "direct" — снова прямо
    longitude: float


@dataclass(frozen=True)
class Eclipse:
    kind: str  # "solar" | "lunar"
    subtype: str | None  # для лунных: penumbral/partial/total
    at: datetime
    longitude: float


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


def sign_of(longitude: float) -> str:
    return SIGNS[int(longitude % 360 // 30)]


def degree_in_sign(longitude: float) -> float:
    return longitude % 30


class Ephemeris:
    """Обёртка над Skyfield: загрузка эфемерид и векторные позиции.

    Если файла эфемерид нет в каталоге, Skyfield скачивает его при создании —
    в образ его кладут заранее.
    """

    def __init__(self, directory: str | os.PathLike) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        loader = Loader(str(directory), verbose=False)
        self.ts = loader.timescale()
        self.eph = loader(EPHEMERIS_FILE)
        self.earth = self.eph["earth"]
        self._targets = {name: self.eph[target] for name, target in _EPH_TARGETS.items()}

    def t(self, moment: datetime):
        return self.ts.from_datetime(moment)

    def _ecliptic(self, body: str, t):
        return self.earth.at(t).observe(self._targets[body]).apparent().frame_latlon(ecliptic_frame)

    def longitude(self, body: str, t) -> np.ndarray | float:
        _, lon, _ = self._ecliptic(body, t)
        return lon.degrees

    def speed(self, body: str, t, delta_days: float = 0.5) -> np.ndarray | float:
        """Скорость по долготе, градусов в сутки (отрицательная — ретроградность)."""
        before = self.longitude(body, self.ts.tt_jd(t.tt - delta_days))
        after = self.longitude(body, self.ts.tt_jd(t.tt + delta_days))
        return ((after - before + 180) % 360 - 180) / (2 * delta_days)

    def gast_degrees(self, moment: datetime) -> float:
        return float(self.t(moment).gast) * 15.0

    # ---------- время ----------

    def t_range(self, start: datetime, end: datetime):
        return self.ts.from_datetime(start), self.ts.from_datetime(end)

    @staticmethod
    def to_dt(t) -> datetime:
        return t.utc_datetime().replace(microsecond=0)

    # ---------- позиции ----------

    def latitude(self, body: str, t) -> np.ndarray | float:
        lat, _, _ = self._ecliptic(body, t)
        return lat.degrees

    def distance_km(self, body: str, t) -> np.ndarray | float:
        _, _, dist = self._ecliptic(body, t)
        return dist.km

    def illumination(self, t) -> np.ndarray | float:
        return almanac.fraction_illuminated(self.eph, "moon", t)

    def elongation(self, t) -> np.ndarray | float:
        """Угол Луна − Солнце по эклиптике, 0..360 (0 — новолуние, 180 — полнолуние)."""
        return (self.longitude("moon", t) - self.longitude("sun", t)) % 360

    # ---------- поиск событий ----------

    def lunations(self, start: datetime, end: datetime) -> list[Lunation]:
        t0, t1 = self.t_range(start, end)
        times, phases = find_discrete(t0, t1, almanac.moon_phases(self.eph))
        kinds = ("new", "first_quarter", "full", "last_quarter")
        lons = np.atleast_1d(self.longitude("moon", times)) if len(times) else []
        return [
            Lunation(kind=kinds[int(p)], at=self.to_dt(t), longitude=float(lon))
            for t, p, lon in zip(times, phases, lons)
        ]

    def ingresses(self, body: str, start: datetime, end: datetime) -> list[Ingress]:
        t0, t1 = self.t_range(start, end)

        def sign_index(t):
            return (self.longitude(body, t) // 30).astype(int) % 12

        sign_index.step_days = 0.25 if body == "moon" else 1.0
        times, values = find_discrete(t0, t1, sign_index)
        return [Ingress(body=body, at=self.to_dt(t), sign=SIGNS[int(v)]) for t, v in zip(times, values)]

    def moon_aspects_to_body(self, body: str, start: datetime, end: datetime) -> list[AspectHit]:
        """Точные мажорные аспекты Луны к движущемуся телу.

        Луна быстрее всех тел, поэтому разность долгот монотонно растёт:
        аспект — момент, когда разность пересекает кратное 30°, входящее в ASPECTS.
        """
        t0, t1 = self.t_range(start, end)

        def sector(t):
            diff = (self.longitude("moon", t) - self.longitude(body, t)) % 360
            return (diff // 30).astype(int)

        sector.step_days = 0.25
        times, values = find_discrete(t0, t1, sector)
        return _aspect_hits(body, times, values, self.to_dt)

    def moon_aspects_to_point(self, name: str, longitude: float, start: datetime, end: datetime) -> list[AspectHit]:
        """Аспекты Луны к неподвижной точке (натальная планета, ASC, MC)."""
        t0, t1 = self.t_range(start, end)

        def sector(t):
            diff = (self.longitude("moon", t) - longitude) % 360
            return (diff // 30).astype(int)

        sector.step_days = 0.25
        times, values = find_discrete(t0, t1, sector)
        return _aspect_hits(name, times, values, self.to_dt)

    def stations(self, body: str, start: datetime, end: datetime) -> list[Station]:
        t0, t1 = self.t_range(start, end)

        def is_retrograde(t):
            return (self.speed(body, t) < 0).astype(int)

        is_retrograde.step_days = 1.0
        times, values = find_discrete(t0, t1, is_retrograde)
        lons = np.atleast_1d(self.longitude(body, times)) if len(times) else []
        return [
            Station(
                body=body,
                at=self.to_dt(t),
                direction="retrograde" if v else "direct",
                longitude=float(lon),
            )
            for t, v, lon in zip(times, values, lons)
        ]

    def is_retrograde(self, body: str, moment: datetime) -> bool:
        return bool(self.speed(body, self.t(moment)) < 0)

    def eclipses(self, start: datetime, end: datetime, lunations: list[Lunation]) -> list[Eclipse]:
        t0, t1 = self.t_range(start, end)
        result: list[Eclipse] = []
        times, kinds, _ = eclipselib.lunar_eclipses(t0, t1, self.eph)
        for t, kind in zip(times, kinds):
            result.append(
                Eclipse(
                    kind="lunar",
                    subtype=LUNAR_ECLIPSE_KINDS.get(int(kind)),
                    at=self.to_dt(t),
                    longitude=float(self.longitude("moon", t)),
                )
            )
        for lunation in lunations:
            if lunation.kind != "new":
                continue
            beta = float(self.latitude("moon", self.t(lunation.at)))
            if abs(beta) < SOLAR_ECLIPSE_MAX_MOON_LATITUDE:
                result.append(Eclipse(kind="solar", subtype=None, at=lunation.at, longitude=lunation.longitude))
        return sorted(result, key=lambda e: e.at)

    def moonrises(self, start: datetime, end: datetime, lat: float, lon: float) -> list[datetime]:
        t0, t1 = self.t_range(start, end)
        observer = self.earth + wgs84.latlon(lat, lon)
        times, rose = almanac.find_risings(observer, self._targets["moon"], t0, t1)
        return [self.to_dt(t) for t, ok in zip(times, rose) if ok]

    def moonsets(self, start: datetime, end: datetime, lat: float, lon: float) -> list[datetime]:
        t0, t1 = self.t_range(start, end)
        observer = self.earth + wgs84.latlon(lat, lon)
        times, ok = almanac.find_settings(observer, self._targets["moon"], t0, t1)
        return [self.to_dt(t) for t, flag in zip(times, ok) if flag]


def _aspect_hits(target: str, times, values, to_dt) -> list[AspectHit]:
    hits = []
    for t, v in zip(times, values):
        angle = int(v) * 30
        aspect = ASPECTS.get(angle)
        if aspect:
            hits.append(AspectHit(target=target, aspect=aspect, angle=angle, at=to_dt(t)))
    return hits
