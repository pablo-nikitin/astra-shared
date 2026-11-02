from dataclasses import dataclass
from enum import StrEnum


class NatalChartHouseSystem(StrEnum):
    PLACIDUS = "placidus"
    PORPHYRY = "porphyry"


class NatalChartPlanetKey(StrEnum):
    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"
    PLUTO = "pluto"
    NORTH_NODE = "north_node"
    LILITH = "lilith"


class NatalChartAspectType(StrEnum):
    CONJUNCTION = "conjunction"
    SEXTILE = "sextile"
    SQUARE = "square"
    TRINE = "trine"
    OPPOSITION = "opposition"


class NatalChartAspectHarmony(StrEnum):
    HARMONIOUS = "harmonious"
    TENSE = "tense"
    NEUTRAL = "neutral"


class NatalChartElement(StrEnum):
    FIRE = "fire"
    EARTH = "earth"
    AIR = "air"
    WATER = "water"


class NatalChartModality(StrEnum):
    CARDINAL = "cardinal"
    FIXED = "fixed"
    MUTABLE = "mutable"


@dataclass(frozen=True)
class SignInfo:
    name: str
    glyph: str
    element: NatalChartElement
    modality: NatalChartModality
    ruler: NatalChartPlanetKey


@dataclass(frozen=True)
class PlanetInfo:
    name: str
    glyph: str
    is_luminary: bool


@dataclass(frozen=True)
class AspectInfo:
    type: NatalChartAspectType
    name: str
    angle: float
    orb: float
    glyph: str
    harmony: NatalChartAspectHarmony


_E = NatalChartElement
_M = NatalChartModality
_P = NatalChartPlanetKey

# Порядок совпадает с astra_shared.astro.SIGNS: индекс знака = долгота // 30.
SIGNS: tuple[SignInfo, ...] = (
    SignInfo("Овен", "♈", _E.FIRE, _M.CARDINAL, _P.MARS),
    SignInfo("Телец", "♉", _E.EARTH, _M.FIXED, _P.VENUS),
    SignInfo("Близнецы", "♊", _E.AIR, _M.MUTABLE, _P.MERCURY),
    SignInfo("Рак", "♋", _E.WATER, _M.CARDINAL, _P.MOON),
    SignInfo("Лев", "♌", _E.FIRE, _M.FIXED, _P.SUN),
    SignInfo("Дева", "♍", _E.EARTH, _M.MUTABLE, _P.MERCURY),
    SignInfo("Весы", "♎", _E.AIR, _M.CARDINAL, _P.VENUS),
    SignInfo("Скорпион", "♏", _E.WATER, _M.FIXED, _P.MARS),
    SignInfo("Стрелец", "♐", _E.FIRE, _M.MUTABLE, _P.JUPITER),
    SignInfo("Козерог", "♑", _E.EARTH, _M.CARDINAL, _P.SATURN),
    SignInfo("Водолей", "♒", _E.AIR, _M.FIXED, _P.SATURN),
    SignInfo("Рыбы", "♓", _E.WATER, _M.MUTABLE, _P.JUPITER),
)

PLANETS: dict[NatalChartPlanetKey, PlanetInfo] = {
    _P.SUN: PlanetInfo("Солнце", "☉", True),
    _P.MOON: PlanetInfo("Луна", "☽", True),
    _P.MERCURY: PlanetInfo("Меркурий", "☿", False),
    _P.VENUS: PlanetInfo("Венера", "♀", False),
    _P.MARS: PlanetInfo("Марс", "♂", False),
    _P.JUPITER: PlanetInfo("Юпитер", "♃", False),
    _P.SATURN: PlanetInfo("Сатурн", "♄", False),
    _P.URANUS: PlanetInfo("Уран", "♅", False),
    _P.NEPTUNE: PlanetInfo("Нептун", "♆", False),
    _P.PLUTO: PlanetInfo("Плутон", "♇", False),
    _P.NORTH_NODE: PlanetInfo("Сев. узел", "☊", False),
    _P.LILITH: PlanetInfo("Лилит", "⚸", False),
}

# Десять классических тел — для баланса стихий/крестов и конфигураций (без узла и Лилит).
CLASSIC_PLANETS: tuple[NatalChartPlanetKey, ...] = tuple(PLANETS)[:10]

_A = NatalChartAspectType
_H = NatalChartAspectHarmony
ASPECTS: tuple[AspectInfo, ...] = (
    AspectInfo(_A.CONJUNCTION, "Соединение", 0.0, 8.0, "☌", _H.NEUTRAL),
    AspectInfo(_A.SEXTILE, "Секстиль", 60.0, 5.0, "⚹", _H.HARMONIOUS),
    AspectInfo(_A.SQUARE, "Квадрат", 90.0, 7.0, "□", _H.TENSE),
    AspectInfo(_A.TRINE, "Тригон", 120.0, 7.0, "△", _H.HARMONIOUS),
    AspectInfo(_A.OPPOSITION, "Оппозиция", 180.0, 8.0, "☍", _H.TENSE),
)
LUMINARY_ORB_BONUS = 1.0
EXACTNESS_ORB_SCALE = 8.0

ELEMENT_NAMES: dict[NatalChartElement, str] = {
    _E.FIRE: "Огонь",
    _E.EARTH: "Земля",
    _E.AIR: "Воздух",
    _E.WATER: "Вода",
}
ELEMENT_COLORS: dict[NatalChartElement, str] = {
    _E.FIRE: "#c0392b",
    _E.EARTH: "#5a8f3c",
    _E.AIR: "#c99a1e",
    _E.WATER: "#2f6fb0",
}
MODALITY_NAMES: dict[NatalChartModality, str] = {
    _M.CARDINAL: "Кардинальный",
    _M.FIXED: "Фиксированный",
    _M.MUTABLE: "Мутабельный",
}

HOUSE_AREAS: dict[int, str] = {
    1: "Облик и подход к жизни",
    2: "Деньги, ресурсы, самоценность",
    3: "Мышление, речь, ближний круг",
    4: "Дом, семья, корни",
    5: "Творчество, любовь, дети",
    6: "Работа, режим, здоровье",
    7: "Партнёрство и близкие",
    8: "Глубина, кризисы, близость",
    9: "Смыслы и дальние горизонты",
    10: "Призвание и карьера",
    11: "Друзья, сообщества, мечты",
    12: "Подсознание и уединение",
}
ANGULAR_HOUSES = frozenset({1, 4, 7, 10})

HOUSE_SYSTEM_NAMES: dict[NatalChartHouseSystem, str] = {
    NatalChartHouseSystem.PLACIDUS: "Placidus",
    NatalChartHouseSystem.PORPHYRY: "Porphyry",
}
