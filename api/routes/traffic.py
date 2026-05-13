"""
Proxy-ruter for alle eksterne API-kall.
Bruker én delt AsyncClient for hele applikasjonen (unngår connection-overhead per request).
"""
import asyncio
import time
from datetime import date as dt_date, timedelta
from pathlib import Path

from fastapi import APIRouter
import httpx

from api.utils.holidays import day_info

router = APIRouter()

# ─── DELT HTTP-KLIENT ────────────────────────────────────────
_http = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=8.0),
    follow_redirects=True,
    headers={"User-Agent": "rushtime.no/1.0"},
)

# ─── TTL-CACHE ───────────────────────────────────────────────
_cache: dict = {}

def _get(key: str, ttl: int):
    e = _cache.get(key)
    if e and (time.monotonic() - e[0]) < ttl:
        return e[1]
    return None

def _set(key: str, val):
    _cache[key] = (time.monotonic(), val)

# ─── MODELL (lazy-load) ──────────────────────────────────────
_model = None
_model_loaded = False
_model_features: list = []

def _load_model_sync():
    p = Path("model/saved/model.pkl")
    if not p.exists():
        return None, []
    import pickle
    with open(p, "rb") as f:
        m = pickle.load(f)
    feats = getattr(m, "feature_name_", None) or getattr(m, "feature_names_", [])
    return m, list(feats)

async def _get_model():
    global _model, _model_loaded, _model_features
    if not _model_loaded:
        loop = asyncio.get_event_loop()
        _model, _model_features = await loop.run_in_executor(None, _load_model_sync)
        _model_loaded = True
    return _model

SCORE_COLORS = {0: "#00ff88", 1: "#8eff5a", 2: "#ffd600", 3: "#ff4d00", 4: "#7b00ff"}

# ─── HELLIGDAGER ─────────────────────────────────────────────
@router.get("/holidays")
async def get_holidays():
    """Returnerer trafikkinfo for i dag + 14 dager frem i tid."""
    result = {}
    today = dt_date.today()
    for i in range(15):
        d = today + timedelta(days=i)
        result[d.isoformat()] = day_info(d)
    return result

# ─── VÆR ─────────────────────────────────────────────────────
@router.get("/weather")
async def get_weather():
    cached = _get("weather", 300)
    if cached is not None:
        return cached
    try:
        r = await _http.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": 59.91, "lon": 10.75},
        )
        r.raise_for_status()
        data = r.json()
        _set("weather", data)
        return data
    except Exception as e:
        print(f"Weather feil: {e}")
        return {"properties": {"timeseries": []}}

# ─── GEOCODE ─────────────────────────────────────────────────
@router.get("/geocode")
async def geocode(q: str):
    if len(q) < 2:
        return []
    try:
        r = await _http.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": f"{q} Oslo Norge",
                "format": "json",
                "limit": 6,
                "addressdetails": 1,
                "countrycodes": "no",
            },
            headers={"Accept-Language": "no", "Referer": "https://rushtime.no"},
        )
        if r.status_code == 200 and r.text.strip():
            return r.json()
        return []
    except Exception as e:
        print(f"Geocode feil: {e}")
        return []

# ─── REVERSE GEOCODE ─────────────────────────────────────────
@router.get("/reverse-geocode")
async def reverse_geocode(lat: float, lon: float):
    try:
        r = await _http.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"Accept-Language": "no"},
        )
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception:
        return {}

# ─── RUTE ────────────────────────────────────────────────────
@router.get("/route")
async def get_route(from_lon: float, from_lat: float, to_lon: float, to_lat: float):
    try:
        r = await _http.get(
            f"https://router.project-osrm.org/route/v1/driving/{from_lon},{from_lat};{to_lon},{to_lat}",
            params={"overview": "full", "geometries": "geojson"},
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Route feil: {e}")
        return {}

# ─── VEIER ───────────────────────────────────────────────────
_OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

@router.get("/roads")
async def get_roads(south: float, west: float, north: float, east: float):
    key = f"roads:{south:.2f},{west:.2f},{north:.2f},{east:.2f}"
    cached = _get(key, 300)
    if cached is not None:
        return cached

    query = (
        f'[out:json][timeout:25];'
        f'way["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        f'({south},{west},{north},{east});out geom;'
    )
    for url in _OVERPASS:
        try:
            r = await _http.post(url, data={"data": query},
                                 timeout=httpx.Timeout(65.0, connect=8.0))
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                _set(key, data)
                return data
            print(f"Overpass {url}: status {r.status_code}")
        except Exception as e:
            print(f"Overpass {url} feil: {e}")
    return {"elements": []}

# ─── PREDIKSJON ──────────────────────────────────────────────
@router.get("/predict")
async def predict(
    hour: int,
    day: int,
    date_str: str = None,
    temp: float = 10.0,
    precip: float = 0.0,
    wind: float = 0.0,
):
    """
    Predikerer trafikkbelastning 0–4.
    Tar hensyn til helligdager, klemmedager og vær i tillegg til ML-modell.
    """
    try:
        check_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    except Exception:
        check_date = dt_date.today()

    dinfo = day_info(check_date)
    factor = dinfo["factor"]

    model = await _get_model()
    if model is not None:
        try:
            import numpy as np
            is_holiday_day = 1 if dinfo["type"] in ("holiday", "bridge", "holiday_period") else 0
            is_weekend = 1 if (day >= 5 or is_holiday_day) else 0
            is_rush_m = 1 if (7 <= hour <= 9 and not is_weekend) else 0
            is_rush_e = 1 if (15 <= hour <= 18 and not is_weekend) else 0
            month = check_date.month
            is_raining = 1 if precip > 0.5 else 0
            is_snowing = 1 if (temp < 0 and precip > 0) else 0
            is_windy = 1 if wind > 8 else 0

            # Prøv med alle features, fall tilbake til færre
            try:
                X = np.array([[hour, day, is_weekend, is_rush_m, is_rush_e, month, 200,
                               temp, precip, wind, is_raining, is_snowing, is_windy]])
                score = int(model.predict(X)[0])
            except Exception:
                X = np.array([[hour, day, is_weekend, is_rush_m, is_rush_e, month, 200]])
                score = int(model.predict(X)[0])

            score = max(0, min(4, round(score * factor)))
            return {"score": score, "color": SCORE_COLORS[score], "day_info": dinfo}
        except Exception as e:
            print(f"Model predict feil: {e}")

    # Heuristisk fallback
    is_off = dinfo["type"] in ("holiday", "bridge", "holiday_period")
    is_rush = (7 <= hour <= 9 or 15 <= hour <= 18) and not is_off and day < 5
    score = 3 if is_rush else (0 if is_off else 1)
    if precip > 1:  score = min(4, score + 1)
    if temp < 0:    score = min(4, score + 1)
    score = max(0, min(4, round(score * factor)))
    return {"score": score, "color": SCORE_COLORS[score], "day_info": dinfo}

# ─── PUNKTER (Vegvesen) ──────────────────────────────────────
@router.get("/points")
async def get_points():
    from api.services.vegvesen import fetch_oslo_points
    return await fetch_oslo_points()
