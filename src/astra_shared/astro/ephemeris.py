"""
Положения светил для натальной карты и лунного календаря.

Все долготы — геоцентрические видимые эклиптические долготы на эпоху даты
(тропический зодиак). Время — UTC (aware datetime).

Эфемериды: JPL DE421 через Skyfield (MIT). Swiss Ephemeris не используем —
она под AGPL, что для сетевого сервиса обязывает открыть весь код.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
from skyfield.api import Loader
from skyfield.framelib import ecliptic_frame

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
