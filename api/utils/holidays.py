"""
Norske offentlige helligdager og trafikkfaktorer.
Beregner påske via Gaussisk algoritme, dekker alle bevegelige og faste helligdager.
"""
from datetime import date, timedelta
from functools import lru_cache


def _easter(year: int) -> date:
    """Gaussisk påskealgoritme — returnerer 1. påskedag."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


_FIXED = {
    (1, 1):   "Nyttårsdag",
    (5, 1):   "Arbeidernes dag",
    (5, 17):  "Grunnlovsdag",
    (12, 24): "Julaften",          # halvdag — trafikken forsvinner fra lunsjtid
    (12, 25): "1. juledag",
    (12, 26): "2. juledag",
    (12, 31): "Nyttårsaften",      # halvdag
}


@lru_cache(maxsize=8)
def _year_holidays(year: int) -> dict:
    """Returnerer dict {date: navn} for alle helligdager i et år."""
    easter = _easter(year)
    h = {
        easter - timedelta(days=3): "Skjærtorsdag",
        easter - timedelta(days=2): "Langfredag",
        easter:                      "1. påskedag",
        easter + timedelta(days=1):  "2. påskedag",
        easter + timedelta(days=39): "Kristi himmelfartsdag",
        easter + timedelta(days=49): "1. pinsedag",
        easter + timedelta(days=50): "2. pinsedag",
    }
    for (month, day), name in _FIXED.items():
        h[date(year, month, day)] = name
    return h


def _all_holidays(year: int) -> dict:
    """Slår sammen helligdager for år og neste (for desember-forhåndsvisning)."""
    h = dict(_year_holidays(year))
    h.update(_year_holidays(year + 1))
    return h


def day_info(d: date) -> dict:
    """
    Returnerer trafikkinfo for en gitt dato:
      type:   'holiday' | 'bridge' | 'weekend' | 'pre_holiday' | 'weekday'
      factor: 0.0–1.3  (multiplikator på trafikkscore)
      name:   helligdagsnavn eller None
      label:  kort tekst for UI-badge eller None
      emoji:  emoji for badge
    """
    holidays = _all_holidays(d.year)

    is_holiday = d in holidays
    is_weekend = d.weekday() >= 5  # lørdag=5, søndag=6
    is_half_day = d in holidays and holidays[d] in ("Julaften", "Nyttårsaften")

    # Klemmedag: virkedag omringet av helligdag/helg på begge sider
    is_bridge = False
    if not is_holiday and not is_weekend:
        prev_off = (d - timedelta(1)) in holidays or (d - timedelta(1)).weekday() >= 5
        next_off = (d + timedelta(1)) in holidays or (d + timedelta(1)).weekday() >= 5
        is_bridge = prev_off and next_off

    # Dag før helligdag (folk drar tidlig, noe høyere trafikk på ettermiddag)
    tomorrow = d + timedelta(1)
    is_pre_holiday = (
        tomorrow in holidays
        and not is_holiday
        and not is_weekend
        and not is_bridge
    )

    name = holidays.get(d)

    # Spesialperioder med ekstra lav trafikk (ferie)
    easter = _easter(d.year)
    in_easter_holiday = easter - timedelta(3) <= d <= easter + timedelta(1)
    in_christmas = date(d.year, 12, 23) <= d <= date(d.year, 12, 31)
    in_summer_holiday = date(d.year, 6, 23) <= d <= date(d.year, 8, 10)

    if is_holiday and is_half_day:
        return {"type": "holiday", "factor": 0.5, "name": name, "label": name, "emoji": "🎅" if "jul" in name.lower() else "🎆"}
    elif is_holiday:
        emoji = _holiday_emoji(name)
        return {"type": "holiday", "factor": 0.1, "name": name, "label": name, "emoji": emoji}
    elif is_bridge:
        return {"type": "bridge", "factor": 0.35, "name": "Klemmedag", "label": "Klemmedag", "emoji": "🏖️"}
    elif in_easter_holiday:
        return {"type": "holiday_period", "factor": 0.2, "name": "Påskeferie", "label": "Påskeferie", "emoji": "🐣"}
    elif in_christmas:
        return {"type": "holiday_period", "factor": 0.25, "name": "Juleferie", "label": "Juleferie", "emoji": "🎄"}
    elif in_summer_holiday:
        return {"type": "summer", "factor": 0.6, "name": "Sommerferie", "label": "Sommerferie", "emoji": "☀️"}
    elif is_weekend:
        return {"type": "weekend", "factor": 0.55, "name": None, "label": None, "emoji": None}
    elif is_pre_holiday:
        label = f"Dagen før {holidays[tomorrow]}"
        return {"type": "pre_holiday", "factor": 1.15, "name": None, "label": label, "emoji": "⚠️"}
    else:
        return {"type": "weekday", "factor": 1.0, "name": None, "label": None, "emoji": None}


def _holiday_emoji(name: str) -> str:
    name = name.lower()
    if "jul" in name:       return "🎄"
    if "nyttår" in name:    return "🎆"
    if "påske" in name or "langfre" in name or "skjær" in name: return "🐣"
    if "pinse" in name:     return "🕊️"
    if "himmelfart" in name: return "✝️"
    if "grunnlov" in name:  return "🇳🇴"
    if "arbeider" in name:  return "✊"
    return "🗓️"
