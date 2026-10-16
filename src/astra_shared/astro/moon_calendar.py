"""
Лунный календарь: раскладывает астрономические события по локальным дням.

MoonCalendar один раз считает события на диапазон дат (с запасом по краям),
а затем отдаёт срезы: день, месяц и персональный слой по натальной карте.
Результат — JSON-совместимые словари с ключами (знаки, планеты, фазы);
человекочитаемые тексты из `moon_calendar_texts` добавляют present_*.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from skyfield.searchlib import find_discrete

from astra_shared.astro import moon_calendar_texts as txt
from astra_shared.astro.ephemeris import (
    PLANETS,
    SUPERMOON_MAX_DISTANCE_KM,
    AspectHit,
    Ephemeris,
    Interval,
    degree_in_sign,
    sign_of,
)
from astra_shared.astro.natal import NatalChart

MOON_CALENDAR_CONTENT_VERSION = txt.CONTENT_VERSION

SLOW_BODIES = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto")
INGRESS_BODIES = ("sun",) + SLOW_BODIES
CARDINAL_SUN_INGRESS = {
    "aries": "spring_equinox",
    "cancer": "summer_solstice",
    "libra": "autumn_equinox",
    "capricorn": "winter_solstice",
}
WEEKDAY_RULERS = ("moon", "mars", "mercury", "jupiter", "venus", "saturn", "sun")  # пн..вс
SIGN_ELEMENTS = {
    "aries": "fire", "leo": "fire", "sagittarius": "fire",
    "taurus": "earth", "virgo": "earth", "capricorn": "earth",
    "gemini": "air", "libra": "air", "aquarius": "air",
    "cancer": "water", "scorpio": "water", "pisces": "water",
}
# Биодинамика (М. Тун): стихия знака Луны -> часть растения.
GARDEN_DAY_TYPES = {"earth": "root", "water": "leaf", "air": "flower", "fire": "fruit"}

# Стрижки: традиционные правила лунных календарей.
HAIRCUT_GOOD_SIGNS = {"taurus", "leo", "virgo"}
HAIRCUT_BAD_SIGNS = {"cancer", "pisces"}
HAIRCUT_BAD_LUNAR_DAYS = {9, 15, 23, 29}

MARGIN = timedelta(days=35)


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    tz: str


class MoonCalendar:
    def __init__(self, ephemeris: Ephemeris, start: date, end: date, location: Location) -> None:
        self.eph = ephemeris
        self.location = location
        self.zone = ZoneInfo(location.tz)
        self.start = start
        self.end = end
        a = self._local_midnight(start) - MARGIN
        b = self._local_midnight(end + timedelta(days=1)) + MARGIN

        self.lunations = ephemeris.lunations(a, b)
        self.moon_ingresses = ephemeris.ingresses("moon", a, b)
        self.moon_aspects = sorted(
            (hit for body in PLANETS if body != "moon" for hit in ephemeris.moon_aspects_to_body(body, a, b)),
            key=lambda h: h.at,
        )
        self.voc = _void_of_course(self.moon_ingresses, self.moon_aspects)
        self.planet_ingresses = sorted(
            (ing for body in INGRESS_BODIES for ing in ephemeris.ingresses(body, a, b)), key=lambda i: i.at
        )
        self.stations = sorted(
            (st for body in SLOW_BODIES for st in ephemeris.stations(body, a, b)), key=lambda s: s.at
        )
        self.eclipses = ephemeris.eclipses(a, b, self.lunations)
        self.moonrises = ephemeris.moonrises(a, b, location.lat, location.lon)
        self.moonsets = ephemeris.moonsets(a, b, location.lat, location.lon)
        self.lunar_day_starts = _lunar_day_starts(self.lunations, self.moonrises)
        self._natal_aspects: dict[tuple, list[AspectHit]] = {}

    # ---------- время ----------

    def _local_midnight(self, d: date) -> datetime:
        return datetime.combine(d, time(0, 0), tzinfo=self.zone).astimezone(ZoneInfo("UTC"))

    def _window(self, d: date) -> tuple[datetime, datetime]:
        return self._local_midnight(d), self._local_midnight(d + timedelta(days=1))

    def _fmt(self, moment: datetime | None) -> str | None:
        return moment.astimezone(self.zone).isoformat(timespec="minutes") if moment else None

    # ---------- день ----------

    def day(self, d: date) -> dict:
        a, b = self._window(d)
        noon = self.eph.t(a + (b - a) / 2)
        elong = float(self.eph.elongation(noon))
        moon_lon = float(self.eph.longitude("moon", noon))
        waxing = elong < 180

        lunations_today = [lun for lun in self.lunations if a <= lun.at < b]
        phase = _phase_key(elong, lunations_today)
        prev_new = max((lun.at for lun in self.lunations if lun.kind == "new" and lun.at <= b), default=None)
        age_days = (a + (b - a) / 2 - prev_new).total_seconds() / 86400 if prev_new else None

        sign_segments = _segments(
            [(ing.at, ing.sign) for ing in self.moon_ingresses], a, b, initial=sign_of(float(self.eph.longitude("moon", self.eph.t(a))))
        )
        lunar_days = _segments(self.lunar_day_starts, a, b)
        voc = [
            {"start": self._fmt(iv.start), "end": self._fmt(iv.end),
             "starts_today": iv.start >= a, "ends_today": iv.end < b}
            for iv in self.voc
            if iv.start < b and iv.end > a
        ]
        aspects = [
            {"target": h.target, "aspect": h.aspect, "angle": h.angle, "at": self._fmt(h.at)}
            for h in self.moon_aspects
            if a <= h.at < b
        ]
        events = self._events(a, b)
        retrogrades = [body for body in SLOW_BODIES if self.eph.is_retrograde(body, a + (b - a) / 2)]

        main_sign = sign_of(moon_lon)
        lunar_numbers = [seg["value"] for seg in lunar_days]
        return {
            "date": d.isoformat(),
            "weekday": d.weekday(),
            "phase": {
                "key": phase,
                "waxing": waxing,
                "illumination": round(float(self.eph.illumination(noon)) * 100, 1),
                "elongation": round(elong, 2),
                "age_days": round(age_days, 1) if age_days is not None else None,
                "lunations": [
                    {"kind": lun.kind, "at": self._fmt(lun.at), "sign": sign_of(lun.longitude),
                     "degree": round(degree_in_sign(lun.longitude), 1)}
                    for lun in lunations_today
                ],
            },
            "moon": {
                "sign": main_sign,
                "longitude": round(moon_lon, 2),
                "distance_km": round(float(self.eph.distance_km("moon", noon))),
            },
            "moon_signs": [self._fmt_segment(s) for s in sign_segments],
            "moonrise": [self._fmt(m) for m in self.moonrises if a <= m < b],
            "moonset": [self._fmt(m) for m in self.moonsets if a <= m < b],
            "lunar_days": [self._fmt_segment(s) for s in lunar_days],
            "void_of_course": voc,
            "aspects": aspects,
            "day_ruler": WEEKDAY_RULERS[d.weekday()],
            "garden": _garden(sign_segments, waxing, lunations_today, self._fmt_segment),
            "haircut": _haircut(main_sign, waxing, lunar_numbers, lunations_today, events),
            "events": events,
            "retrogrades": retrogrades,
        }

    def _fmt_segment(self, seg: dict) -> dict:
        return {"value": seg["value"], "start": self._fmt(seg["start"]), "end": self._fmt(seg["end"])}

    def _events(self, a: datetime, b: datetime) -> list[dict]:
        events: list[dict] = []
        for lun in self.lunations:
            if a <= lun.at < b and lun.kind in ("new", "full"):
                dist = float(self.eph.distance_km("moon", self.eph.t(lun.at)))
                events.append({
                    "type": "lunation", "kind": lun.kind, "at": self._fmt(lun.at),
                    "sign": sign_of(lun.longitude), "degree": round(degree_in_sign(lun.longitude), 1),
                    "supermoon": dist < SUPERMOON_MAX_DISTANCE_KM,
                })
        for ecl in self.eclipses:
            if a <= ecl.at < b:
                events.append({
                    "type": "eclipse", "kind": ecl.kind, "subtype": ecl.subtype, "at": self._fmt(ecl.at),
                    "sign": sign_of(ecl.longitude), "degree": round(degree_in_sign(ecl.longitude), 1),
                })
        for ing in self.planet_ingresses:
            if a <= ing.at < b:
                event = {"type": "ingress", "body": ing.body, "sign": ing.sign, "at": self._fmt(ing.at)}
                if ing.body == "sun" and ing.sign in CARDINAL_SUN_INGRESS:
                    event["season"] = CARDINAL_SUN_INGRESS[ing.sign]
                events.append(event)
        for st in self.stations:
            if a <= st.at < b:
                events.append({
                    "type": "station", "body": st.body, "direction": st.direction, "at": self._fmt(st.at),
                    "sign": sign_of(st.longitude),
                })
        return sorted(events, key=lambda e: e["at"])

    # ---------- месяц ----------

    def month(self, year: int, month: int) -> dict:
        first = date(year, month, 1)
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days = []
        d = first
        while d <= last:
            day = self.day(d)
            days.append({
                "date": day["date"],
                "phase": day["phase"]["key"],
                "waxing": day["phase"]["waxing"],
                "illumination": day["phase"]["illumination"],
                "elongation": day["phase"]["elongation"],
                "moon_sign": day["moon"]["sign"],
                "markers": sorted({e["type"] if e["type"] != "lunation" else e["kind"] + "_moon" for e in day["events"]}),
                "haircut": day["haircut"]["verdict"],
                "garden": day["garden"]["status"],
            })
            d += timedelta(days=1)
        a, b = self._window(first)[0], self._window(last)[1]
        return {
            "year": year,
            "month": month,
            "days": days,
            "overview": {
                "lunations": [
                    {"kind": lun.kind, "at": self._fmt(lun.at), "sign": sign_of(lun.longitude)}
                    for lun in self.lunations if a <= lun.at < b and lun.kind in ("new", "full")
                ],
                "eclipses": [
                    {"kind": e.kind, "subtype": e.subtype, "at": self._fmt(e.at), "sign": sign_of(e.longitude)}
                    for e in self.eclipses if a <= e.at < b
                ],
                "stations": [
                    {"body": s.body, "direction": s.direction, "at": self._fmt(s.at), "sign": sign_of(s.longitude)}
                    for s in self.stations if a <= s.at < b
                ],
                "retrogrades_at_start": [body for body in SLOW_BODIES if self.eph.is_retrograde(body, a)],
                "best_haircut_days": [x["date"] for x in days if x["haircut"] == "good"],
                "sowing_days": [x["date"] for x in days if x["garden"] == "sow"],
                "void_of_course_hours": round(
                    sum(
                        (min(iv.end, b) - max(iv.start, a)).total_seconds()
                        for iv in self.voc if iv.start < b and iv.end > a
                    ) / 3600
                ),
            },
        }

    # ---------- персональный слой ----------

    def personal_day(self, d: date, natal: NatalChart) -> dict:
        a, b = self._window(d)
        hits = self._natal_hits(natal)
        houses = self._house_segments(natal, a, b)
        aspects = [
            {"target": h.target, "aspect": h.aspect, "angle": h.angle, "at": self._fmt(h.at)}
            for h in hits if a <= h.at < b
        ]
        noon_lon = float(self.eph.longitude("moon", self.eph.t(a + (b - a) / 2)))
        lunation_house = [
            {"kind": lun.kind, "house": natal.house_of(lun.longitude), "sign": sign_of(lun.longitude)}
            for lun in self.lunations if a <= lun.at < b and lun.kind in ("new", "full")
        ]
        return {
            "date": d.isoformat(),
            "house_system": natal.house_system,
            "moon_houses": [self._fmt_segment(s) for s in houses],
            "main_house": natal.house_of(noon_lon),
            "aspects": aspects,
            "moon_in_sun_sign": sign_of(noon_lon) == natal.sun_sign,
            "moon_in_moon_sign": sign_of(noon_lon) == natal.moon_sign,
            "lunar_return": any(h["target"] == "moon" and h["aspect"] == "conjunction" for h in aspects),
            "lunations": lunation_house,
        }

    def _natal_hits(self, natal: NatalChart) -> list[AspectHit]:
        # Ключ — сами натальные долготы: id() объекта мог бы переиспользоваться после сборки мусора.
        key = tuple(sorted(natal.aspect_points().items()))
        if key not in self._natal_aspects:
            a = self._local_midnight(self.start) - timedelta(days=1)
            b = self._local_midnight(self.end + timedelta(days=1)) + timedelta(days=1)
            hits = [
                hit
                for name, lon in natal.aspect_points().items()
                for hit in self.eph.moon_aspects_to_point(name, lon, a, b)
            ]
            self._natal_aspects[key] = sorted(hits, key=lambda h: h.at)
        return self._natal_aspects[key]

    def _house_segments(self, natal: NatalChart, a: datetime, b: datetime) -> list[dict]:
        cusps = np.array(natal.cusps)
        spans = (np.roll(cusps, -1) - cusps) % 360

        def house(t):
            lons = np.atleast_1d(self.eph.longitude("moon", t))
            inside = ((lons[:, None] - cusps[None, :]) % 360) < spans[None, :]
            return np.argmax(inside, axis=1) + 1

        house.step_days = 0.1
        t0, t1 = self.eph.t_range(a, b)
        times, values = find_discrete(t0, t1, house)
        transitions = [(self.eph.to_dt(t), int(v)) for t, v in zip(times, values)]
        return _segments(transitions, a, b, initial=int(house(t0)[0]))


# ---------- чистые функции ----------


def _phase_key(elongation: float, lunations_today: list) -> str:
    if lunations_today:
        return lunations_today[0].kind
    if elongation < 90:
        return "waxing_crescent"
    if elongation < 180:
        return "waxing_gibbous"
    if elongation < 270:
        return "waning_gibbous"
    return "waning_crescent"


def _segments(transitions: list[tuple[datetime, object]], a: datetime, b: datetime, initial=None) -> list[dict]:
    """Режет ступенчатую функцию (момент смены -> значение) на куски внутри [a, b).

    start=None — значение действовало ещё до начала дня, end=None — продолжится после.
    """
    moments = [m for m, _ in transitions]
    idx = bisect_right(moments, a) - 1
    current = transitions[idx][1] if idx >= 0 else initial
    segments = [{"value": current, "start": None, "end": None}]
    for moment, value in transitions[idx + 1:]:
        if moment >= b:
            break
        segments[-1]["end"] = moment
        segments.append({"value": value, "start": moment, "end": None})
    return segments


def _void_of_course(ingresses, aspects: list[AspectHit]) -> list[Interval]:
    """Луна без курса: от последнего точного аспекта в знаке до входа в следующий знак."""
    intervals = []
    aspect_times = [h.at for h in aspects]
    for prev, nxt in zip(ingresses, ingresses[1:]):
        i = bisect_right(aspect_times, nxt.at) - 1
        last = aspect_times[i] if i >= 0 else None
        start = last if last and last >= prev.at else prev.at
        intervals.append(Interval(start=start, end=nxt.at))
    return intervals


def _lunar_day_starts(lunations, moonrises: list[datetime]) -> list[tuple[datetime, int]]:
    """Лунные сутки: 1-е — от новолуния до ближайшего восхода Луны, далее от восхода до восхода."""
    events = sorted(
        [(lun.at, "new") for lun in lunations if lun.kind == "new"] + [(m, "rise") for m in moonrises]
    )
    starts: list[tuple[datetime, int]] = []
    number = None
    for moment, kind in events:
        if kind == "new":
            number = 1
        elif number is not None:
            number += 1
        else:
            continue
        starts.append((moment, number))
    return starts


def _garden(sign_segments: list[dict], waxing: bool, lunations_today: list, fmt) -> dict:
    rest = any(lun.kind in ("new", "full") for lun in lunations_today)
    if rest:
        status = "rest"
    else:
        status = "sow" if waxing else "tend"
    return {
        "status": status,
        "waxing": waxing,
        "types": [
            fmt({"value": GARDEN_DAY_TYPES[SIGN_ELEMENTS[s["value"]]], "start": s["start"], "end": s["end"]})
            for s in sign_segments
        ],
    }


def _haircut(sign: str, waxing: bool, lunar_days: list[int], lunations_today: list, events: list[dict]) -> dict:
    reasons: list[str] = []
    if any(lun.kind in ("new", "full") for lun in lunations_today):
        reasons.append("lunation")
    if any(e["type"] == "eclipse" for e in events):
        reasons.append("eclipse")
    bad_days = sorted(set(lunar_days) & HAIRCUT_BAD_LUNAR_DAYS)
    if bad_days:
        reasons.append("lunar_day")
    if sign in HAIRCUT_BAD_SIGNS:
        reasons.append("bad_sign")

    if reasons:
        verdict = "bad"
    elif sign in HAIRCUT_GOOD_SIGNS:
        verdict = "good"
        reasons.append("good_sign")
    else:
        verdict = "neutral"
    return {
        "verdict": verdict,
        "reasons": reasons,
        "growth": "faster" if waxing else "slower",
        "sign": sign,
        "bad_lunar_days": bad_days,
    }


# ---------- тексты ----------


def _time(iso: str | None) -> str | None:
    return datetime.fromisoformat(iso).strftime("%H:%M") if iso else None


def _sign(key: str) -> dict:
    return {"key": key, **txt.SIGNS[key]}


def _day_month(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {_MONTHS_GENITIVE[d.month - 1]}"


_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def present_day(day: dict) -> dict:
    phase = day["phase"]
    main_sign = day["moon"]["sign"]
    return {
        "date": day["date"],
        "title": txt.PHASES[phase["key"]]["short"],
        "headline": txt.MOON_IN_SIGN[main_sign]["headline"],
        "phase": {
            "key": phase["key"],
            "name": txt.PHASES[phase["key"]]["name"],
            "text": txt.PHASES[phase["key"]]["text"],
            "waxing": phase["waxing"],
            "illumination": phase["illumination"],
            "elongation": phase["elongation"],
            "age_days": phase["age_days"],
            "lunations": [{**lun, "time": _time(lun["at"])} for lun in phase["lunations"]],
        },
        "moon": {**day["moon"], "sign": _sign(main_sign)},
        "moonrise": [_time(m) for m in day["moonrise"]],
        "moonset": [_time(m) for m in day["moonset"]],
        "lunar_days": [
            {"number": seg["value"], **txt.LUNAR_DAYS[min(seg["value"], 30)],
             "favorable": min(seg["value"], 30) not in txt.UNFAVORABLE_LUNAR_DAYS,
             "from": _time(seg["start"]), "until": _time(seg["end"])}
            for seg in day["lunar_days"]
        ],
        "moon_signs": [
            {**_sign(seg["value"]), "title": f"Луна {txt.SIGNS[seg['value']]['in']}",
             "text": txt.MOON_IN_SIGN[seg["value"]]["text"],
             "from": _time(seg["start"]), "until": _time(seg["end"])}
            for seg in day["moon_signs"]
        ],
        "void_of_course": {
            "intervals": [
                {"from": _time(iv["start"]) if iv["starts_today"] else None,
                 "until": _time(iv["end"]) if iv["ends_today"] else None,
                 "from_date": iv["start"], "until_date": iv["end"]}
                for iv in day["void_of_course"]
            ],
            "text": txt.VOID_OF_COURSE["text"] if day["void_of_course"] else txt.VOID_OF_COURSE["none"],
        },
        "aspects": [
            {"title": f"{txt.ASPECTS[a['aspect']]['name']} с {txt.PLANETS[a['target']]['with']}",
             "glyph": f"☽ {txt.ASPECTS[a['aspect']]['glyph']} {txt.PLANETS[a['target']]['glyph']}",
             "aspect": a["aspect"], "target": a["target"],
             "tone": txt.ASPECTS[a["aspect"]]["tone"], "time": _time(a["at"]),
             "aspect_text": txt.ASPECTS[a["aspect"]]["text"], "theme": txt.PLANET_THEMES[a["target"]],
             "text": f"{txt.ASPECTS[a['aspect']]['text']} Тема: {txt.PLANET_THEMES[a['target']]}."}
            for a in day["aspects"]
        ],
        "day_ruler": {
            "key": day["day_ruler"], "name": txt.PLANETS[day["day_ruler"]]["name"],
            "glyph": txt.PLANETS[day["day_ruler"]]["glyph"],
            "weekday": txt.DAY_RULERS[day["day_ruler"]]["weekday"],
            "text": txt.DAY_RULERS[day["day_ruler"]]["text"],
            "colors": list(txt.DAY_RULERS[day["day_ruler"]]["colors"]),
        },
        "garden": {
            "status": day["garden"]["status"],
            **txt.GARDEN["status"][day["garden"]["status"]],
            "types": [
                {"key": seg["value"], **txt.GARDEN["types"][seg["value"]],
                 "from": _time(seg["start"]), "until": _time(seg["end"])}
                for seg in day["garden"]["types"]
            ],
        },
        "haircut": {
            "verdict": day["haircut"]["verdict"],
            "label": txt.HAIRCUT["verdict"][day["haircut"]["verdict"]],
            "reasons": [txt.HAIRCUT["reasons"][r] for r in day["haircut"]["reasons"]],
            "growth": txt.HAIRCUT["growth"][day["haircut"]["growth"]],
        },
        "events": [_present_event(e) for e in day["events"]],
        "retrogrades": [{"key": b, "name": txt.PLANETS[b]["name"], "glyph": txt.PLANETS[b]["glyph"]} for b in day["retrogrades"]],
    }


def _present_event(e: dict) -> dict:
    sign_in = txt.SIGNS[e["sign"]]["in"]
    if e["type"] == "lunation":
        title = txt.EVENTS["lunation"][e["kind"]].format(in_sign=sign_in)
        if e.get("supermoon"):
            title += " · " + txt.EVENTS["lunation"]["supermoon"]
        text = txt.EVENTS["lunation"]["text_" + e["kind"]].format(theme=txt.SIGN_THEMES[e["sign"]])
        kind = e["kind"] + "_moon"
    elif e["type"] == "eclipse":
        title = txt.EVENTS["eclipse"][e["kind"]].format(in_sign=sign_in)
        if e.get("subtype"):
            title += f" ({txt.EVENTS['eclipse']['subtype'][e['subtype']]})"
        text = txt.EVENTS["eclipse"]["text"]
        kind = "eclipse"
    elif e["type"] == "ingress":
        title = txt.EVENTS["season"].get(e.get("season")) or txt.EVENTS["ingress"].format(
            planet=txt.PLANETS[e["body"]]["name"], in_sign=sign_in
        )
        if e.get("season"):
            title += f" · Солнце {sign_in}"
        text = f"Тема: {txt.PLANET_THEMES[e['body']]} — теперь в ключе «{txt.SIGN_THEMES[e['sign']]}»."
        kind = "ingress"
    else:
        planet = txt.PLANETS[e["body"]]["name"]
        title = txt.EVENTS["station"][e["direction"]].format(planet=planet) + f" {sign_in}"
        text = txt.EVENTS["station"]["text_" + e["direction"]].format(theme=txt.PLANET_THEMES[e["body"]])
        kind = "retrograde" if e["direction"] == "retrograde" else "direct"
    return {"kind": kind, "title": title, "text": text, "time": _time(e["at"])}


def present_personal(personal: dict) -> dict:
    notes = []
    if personal["house_system"] == "solar":
        notes.append(txt.PERSONAL["solar_houses_note"])
    if personal["lunar_return"]:
        notes.append(txt.PERSONAL["lunar_return"])
    if personal["moon_in_sun_sign"]:
        notes.append(txt.PERSONAL["moon_in_sun_sign"])
    if personal["moon_in_moon_sign"]:
        notes.append(txt.PERSONAL["moon_in_moon_sign"])
    for lun in personal["lunations"]:
        notes.append(txt.PERSONAL["lunation_in_house"].format(
            kind="Новолуние" if lun["kind"] == "new" else "Полнолуние",
            house=lun["house"], house_theme=txt.HOUSE_THEMES[lun["house"]],
        ))
    return {
        "main_house": personal["main_house"],
        "houses": [
            {"house": seg["value"], **txt.HOUSES[seg["value"]], "from": _time(seg["start"]), "until": _time(seg["end"])}
            for seg in personal["moon_houses"]
        ],
        "aspects": [
            {"title": f"{txt.ASPECTS[a['aspect']]['name']} Луны с {txt.PLANETS[a['target']]['with_your']}",
             "glyph": f"☽ {txt.ASPECTS[a['aspect']]['glyph']} {txt.PLANETS[a['target']]['glyph']}",
             "aspect": a["aspect"], "target": a["target"],
             "tone": txt.ASPECTS[a["aspect"]]["tone"], "time": _time(a["at"]),
             "aspect_text": txt.ASPECTS[a["aspect"]]["text"], "theme": txt.PLANET_THEMES[a["target"]],
             "text": f"{txt.ASPECTS[a['aspect']]['text']} Затронуто: {txt.PLANET_THEMES[a['target']]}."}
            for a in personal["aspects"]
        ],
        "notes": notes,
    }


def present_month(month: dict) -> dict:
    ov = month["overview"]
    parts = []
    lunations = [
        f"{'новолуние' if lun['kind'] == 'new' else 'полнолуние'} {txt.SIGNS[lun['sign']]['in']} {_day_month(lun['at'])}"
        for lun in ov["lunations"]
    ]
    if lunations:
        parts.append(f"В {txt.MONTHS_PREPOSITIONAL[month['month'] - 1]}: " + ", ".join(lunations) + ".")
    for e in ov["eclipses"]:
        name = "Солнечное" if e["kind"] == "solar" else "Лунное"
        parts.append(f"{name} затмение {txt.SIGNS[e['sign']]['in']} {_day_month(e['at'])} — время больших перемен.")
    for s in ov["stations"]:
        verb = "разворачивается назад" if s["direction"] == "retrograde" else "снова идёт прямо"
        parts.append(f"{txt.PLANETS[s['body']]['name']} {verb} {_day_month(s['at'])}.")
    if ov["best_haircut_days"]:
        days = ", ".join(str(date.fromisoformat(d).day) for d in ov["best_haircut_days"])
        parts.append(f"Лучшие дни для стрижки: {days}.")
    parts.append(f"Луна без курса — около {ov['void_of_course_hours']} ч за месяц.")
    return {
        "title": f"{txt.MONTHS_NOMINATIVE[month['month'] - 1]}, {month['year']}",
        "days": month["days"],
        "overview": {**ov, "text": " ".join(parts)},
    }
