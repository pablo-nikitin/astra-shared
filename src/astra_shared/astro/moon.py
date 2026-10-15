"""
Фаза Луны на календарные дни в часовом поясе пользователя.

День, в который наступает главная фаза (новолуние, первая четверть,
полнолуние, последняя четверть), называется по ней; остальные дни — по
промежуточной фазе из элонгации в местный полдень. Освещённость, возраст и
«растёт/убывает» — тоже на полдень, чтобы иконка не прыгала на границе суток.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from skyfield import almanac
from skyfield.searchlib import find_discrete

from astra_shared.astro.ephemeris import Ephemeris

LUNATION_KEYS = ("new_moon", "first_quarter", "full_moon", "last_quarter")

# Синодический месяц ~29.53 суток: за окно чуть длиннее него перед периодом
# гарантированно попадает последнее новолуние для возраста Луны.
_LOOKBACK_DAYS = 31


@dataclass(frozen=True)
class MoonPhase:
    key: str  # LUNATION_KEYS или waxing_crescent | waxing_gibbous | waning_gibbous | waning_crescent
    illumination: float  # 0..1
    age_days: float  # сутки с последнего новолуния
    is_waxing: bool


def _intermediate_key(elongation: float) -> str:
    if elongation < 90:
        return "waxing_crescent"
    if elongation < 180:
        return "waxing_gibbous"
    if elongation < 270:
        return "waning_gibbous"
    return "waning_crescent"


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=zone).astimezone(UTC)


def moon_phases(ephemeris: Ephemeris, first: date, last: date, tz: str) -> dict[date, MoonPhase]:
    """Фаза Луны на каждый день first..last включительно."""
    zone = ZoneInfo(tz)
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    bounds = [_local_midnight(day, zone) for day in days] + [_local_midnight(last + timedelta(days=1), zone)]
    noons = [start + (end - start) / 2 for start, end in zip(bounds, bounds[1:])]

    times, phases = find_discrete(
        ephemeris.t(bounds[0] - timedelta(days=_LOOKBACK_DAYS)),
        ephemeris.t(bounds[-1]),
        almanac.moon_phases(ephemeris.eph),
    )
    lunations = [(moment, int(phase)) for moment, phase in zip(times.utc_datetime(), phases)]

    t_noons = ephemeris.ts.from_datetimes(noons)
    elongations = np.atleast_1d((ephemeris.longitude("moon", t_noons) - ephemeris.longitude("sun", t_noons)) % 360)
    illuminations = np.atleast_1d(almanac.fraction_illuminated(ephemeris.eph, "moon", t_noons))

    result = {}
    for index, day in enumerate(days):
        start, end, noon = bounds[index], bounds[index + 1], noons[index]
        today = [phase for moment, phase in lunations if start <= moment < end]
        last_new = max(moment for moment, phase in lunations if phase == 0 and moment <= noon)
        elongation = float(elongations[index])
        result[day] = MoonPhase(
            key=LUNATION_KEYS[today[0]] if today else _intermediate_key(elongation),
            illumination=round(float(illuminations[index]), 3),
            age_days=round((noon - last_new).total_seconds() / 86_400, 2),
            is_waxing=elongation < 180,
        )
    return result
